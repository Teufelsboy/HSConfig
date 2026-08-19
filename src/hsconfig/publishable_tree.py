"""Pure publishable-tree policy and its bounded Git/filesystem inventory adapter."""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping, Sequence
import hashlib
import html
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from typing import Any, Literal, NamedTuple
import unicodedata
from urllib.parse import unquote, urlsplit

import yaml

from hsconfig.version import __version__


PublishableTreeMode = Literal[
    "working-pre-cutover",
    "candidate-index",
    "candidate",
    "final",
]

_ROW_FIELDS = frozenset(
    {
        "path",
        "git_mode",
        "entry_kind",
        "tracked",
        "blob_oid",
        "content_sha256",
        "content",
    }
)
_BASELINE_FIELDS = frozenset({"schema_version", "count", "aggregate_sha256"})
_ALLOWED_DIRECTORY_ROOTS = frozenset({".github", "docs", "scripts", "src", "tests"})
_ALLOWED_ROOT_FILES = frozenset(
    {
        ".gitattributes",
        ".gitignore",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "constraints-ci.txt",
        "LICENSE",
        "pylock.3.11.toml",
        "pylock.3.12.toml",
        "pyproject.toml",
        "README.md",
        "SECURITY.md",
    }
)
_ALLOWED_DOC_ROOTS = frozenset({"architecture", "contracts", "operator"})
_LEGACY_PREFIXES = (
    ".agents/",
    ".superpowers/",
    "docs/history/",
    "docs/research/",
    "docs/superpowers/",
)
_OBSOLETE_OPERATOR_PATHS = frozenset(
    {
        "docs/operator/autonomous-source-builder-next.md",
        "docs/operator/boarlock-fracking-source-decision.md",
        "docs/operator/git-branch-cleanup-audit-2026-07-17.md",
        "docs/operator/kingslayer-quick-pick-source-decision.md",
        "docs/operator/source-backed-strong-closure.md",
        "docs/operator/source-builder-workflow.md",
        "docs/operator/universal-wild-no-block-contract.md",
    }
)
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{index}" for index in range(1, 10)), *(f"LPT{index}" for index in range(1, 10))}
)
_MARKDOWN_SCHEME_AUTOLINK = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]{1,31}:")
_MARKDOWN_EMAIL_AUTOLINK = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_MARKDOWN_LIST_BLOCK_START = re.compile(
    r"^(?:[-+*]|\d{1,9}[.)])(?:[ \t]+|$)"
)
_MARKDOWN_SETEXT_UNDERLINE = re.compile(r"^(?:=+|-+)[ \t]*$")
_MARKDOWN_REFERENCE_DEFINITION_START = re.compile(
    r"^\[(?:\\.|[^\[\]\\]){1,999}\]:"
)
_MARKDOWN_RAW_TEXT_HTML_BLOCK = re.compile(
    r"^<(?:script|pre|style|textarea)(?:\s|>|$)",
    re.IGNORECASE,
)
_MARKDOWN_HTML_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "base",
        "basefont",
        "blockquote",
        "body",
        "caption",
        "center",
        "col",
        "colgroup",
        "dd",
        "details",
        "dialog",
        "dir",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "frame",
        "frameset",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "head",
        "header",
        "hr",
        "html",
        "iframe",
        "legend",
        "li",
        "link",
        "main",
        "menu",
        "menuitem",
        "nav",
        "noframes",
        "ol",
        "optgroup",
        "option",
        "p",
        "param",
        "search",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "title",
        "tr",
        "track",
        "ul",
    }
)
_MARKDOWN_HTML_BLOCK_TAG = re.compile(
    r"^</?([A-Za-z][A-Za-z0-9-]*)(?:\s|/?>|$)",
    re.IGNORECASE,
)
_MARKDOWN_COMPLETE_HTML_TAG = re.compile(
    r"^(?:"
    r"<[A-Za-z][A-Za-z0-9-]*"
    r"(?:\s+[A-Za-z_:][A-Za-z0-9_.:-]*"
    r"(?:\s*=\s*(?:[^\s\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*"
    r"\s*/?>"
    r"|</[A-Za-z][A-Za-z0-9-]*\s*>"
    r")\s*$"
)
_MARKDOWN_MAX_DEPTH = 32
_MARKDOWN_WORK_FACTOR = 32
_MARKDOWN_LINK_WHITESPACE = " \t\r\n"
_HTML5_SPACE = " \t\r\n\f"
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_MAX_FILE_BYTES = 128 * 1024 * 1024
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
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|"
        r"credential|private[_-]?key|auth(?:[_-]?(?:token|material))?|session)\b"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9+/=_\-.]{24,}[\"']?"
    ),
)
_RESIDUE_COMPONENT = re.compile(
    r"(?i)(?:^|[/\\])(?:__pycache__|\.cache|\.hypothesis|\.pytest_cache|"
    r"\.ruff_cache|\.mypy_cache|\.tox|\.nox|\.idea|\.vscode|build|dist|tmp|temp|"
    r"\.staging[^/\\]*|\.codex-qa(?:[-_.][^/\\]+)?|staging|backup|backups|obsolete|old_generation)"
    r"(?:$|[/\\])"
)
_RESIDUE_SUFFIX = re.compile(
    r"(?i)(?:\.bak|\.backup|\.old|\.orig|\.pyc|\.pyo|\.swp|\.swo|\.tmp|~)$"
)
_PLACEHOLDER_WORDS = ("T" + "BD", "TO" + "DO", "FIX" + "ME")
_PLACEHOLDER = re.compile(
    r"\b(?:" + "|".join(_PLACEHOLDER_WORDS) + r")\b", re.IGNORECASE
)
_EXPLICIT_PLACEHOLDER = re.compile(r"\bPLACE" + r"HOLDER\b", re.IGNORECASE)
_ACTIVE_SOURCE_SUFFIXES = frozenset(
    {
        ".bat",
        ".c",
        ".cc",
        ".cmd",
        ".cpp",
        ".cs",
        ".go",
        ".h",
        ".hpp",
        ".java",
        ".js",
        ".jsx",
        ".ps1",
        ".py",
        ".pyi",
        ".rb",
        ".rs",
        ".sh",
        ".ts",
        ".tsx",
        ".zsh",
    }
)
_SENSITIVE_SUFFIXES = {".jks", ".key", ".keystore", ".p12", ".pem", ".pfx", ".ppk"}
_SECRET_NAME = re.compile(
    r"(?i)(?:^|[._-])(?:id_(?:dsa|ecdsa|ed25519|rsa)|api[-_]?(?:key|token)|"
    r"auth[-_]?(?:key|token)|access[-_]?token|client[-_]?(?:key|secret|token)|"
    r"private[-_]?key|secret|credentials?|password|passwd|token)(?:[._-]|$)"
)
_RUNTIME_COMPACT = {
    "hdt" + "export",
    "hdt" + "replay",
    "hearthrangerlog",
    "hearthrangerlogs",
    "hearthstonelog",
    "hearthstonelogs",
    "hs" + "replay",
    "power" + "log",
    "privateruntime",
    "runtimeevidence",
    "runtimeexport",
    "runtimeexports",
}
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

# Public compatibility surfaces used by the canonical release-gate wrapper.
SOURCE_TODO_ALLOWLIST: tuple[Mapping[str, Any], ...] = ()
EXACT_PLACEHOLDER_REFERENCE_SHA256: Mapping[str, Mapping[int, str]] = {
    "docs/operator/README.md": {
        715: "d0997da82e0ae641345085fcd2f3a0588c763e75f1c909f1a3826100f82da77b"
    },
    "src/hsconfig/cli_parser.py": {
        64: "6eea5855f7b68a28d9837b43338ef1c9c64370e9f3dae6d583509dfb8dcdcbac",
        89: "894d8f6d55a35c4e9426fe29de30db2333f5b3797ee24587b272d034ab7e7562",
        128: "d11fe3f4881b01ce66c0f8ef09778e84f182aa2d571c42f9cd4b8fae4bf9eff7",
        161: "ab157ec4b7902309bb5029142aca743511e43587fdf753f52668750b788101cc",
        171: "cace9a43ddb95629998271a922872430b8e5230b0e25c2b335d910c63b08e4dd",
        185: "c601aab16f8d343ec912c1b44d6bbba7832bc43b89a87e92536f3355c2a10e0c",
        198: "ba0492c2907f7e3596bb82298d6eab7bd238c8197c84be310c900d5a1eaf2520",
        216: "eb0b21eea338c4ac38770df1932764f86eb4bc334bf51f2345d7ddca3662d098",
        237: "87078ccbe89f5d5a0aa0a0f7601ce6e71b6b4015b316ad220164abb0151cfd89",
        251: "bc2e3a70c28a3eabbc1bd0747bf8fb7582a68cb66b0e3dc729c3c07b3a7ec78a",
    },
    "src/hsconfig/deck_input_verification.py": {
        33: "c6b238e40c24b6c239e0c07fdb6857cc0cf1e11e3682d50dff5a7be65866af05"
    },
    "src/hsconfig/input_loading.py": {
        54: "e516377413d0908ed7d5e0cedea28b5b864dedf3257df578f923d5c6a8e7aa61",
        388: "9d7d05b9b495a5faadcdc475bb0a30a7ffda56c392e6c4959f9d14270b66b49d",
        390: "2833fa4aeaf243cd7e22b3e1cd39fa3548eaba6da868b82d7b4b64f0c9a0509b",
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
}

WORKING_PRE_CUTOVER_LEGACY_BASELINE: Mapping[str, object] = {
    "schema_version": 1,
    "count": 538,
    "aggregate_sha256": "e512a342802139b4f61dc5e9a216b1c840f833fa35b924077647fcaa042f5e9d",
}


class PublishableTreeError(ValueError):
    """Raised when the inventory cannot be captured or normalized safely."""


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for character in value:
        counts[character] = counts.get(character, 0) + 1
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


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
        quote = value[start] if value[start] in {'"', "'"} else None
        if quote is None:
            token = re.match(r"\S+", value[start:])
            if token is not None:
                candidate = token.group(0)
                code_expression = (
                    '"' in candidate
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
        for character in value[start + 1 :]:
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
    except (json.JSONDecodeError, UnicodeError, RecursionError, MemoryError) as error:
        raise PublishableTreeError("invalid structured JSON content") from error
    candidates: list[str] = []
    pending: list[tuple[Any, int]] = [(document, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > _MAX_STRUCTURED_DEPTH:
            raise PublishableTreeError("structured JSON content exceeds depth limit")
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
                raise PublishableTreeError("structured YAML event count exceeds limit")
        return event

    def compose_document(self) -> yaml.nodes.Node:
        self._yaml_documents += 1
        if self._yaml_documents > _MAX_YAML_DOCUMENTS:
            raise PublishableTreeError("structured YAML document count exceeds limit")
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
                raise PublishableTreeError("structured YAML alias count exceeds limit")
        else:
            self._yaml_nodes += 1
            if self._yaml_nodes > _MAX_YAML_NODES:
                raise PublishableTreeError("structured YAML node count exceeds limit")
            anchor = getattr(event, "anchor", None)
            if anchor is not None:
                if len(anchor) > 128:
                    raise PublishableTreeError(
                        "structured YAML anchor name exceeds limit"
                    )
                self._yaml_anchors += 1
                if self._yaml_anchors > _MAX_YAML_ANCHORS:
                    raise PublishableTreeError(
                        "structured YAML anchor count exceeds limit"
                    )
            tag = getattr(event, "tag", None)
            if tag is not None and len(tag) > 256:
                raise PublishableTreeError("structured YAML tag exceeds limit")
        self._yaml_depth += 1
        if self._yaml_depth > _MAX_STRUCTURED_DEPTH:
            raise PublishableTreeError("structured YAML content exceeds depth limit")
        try:
            return super().compose_node(parent, index)
        finally:
            self._yaml_depth -= 1

    def compose_scalar_node(self, anchor: str | None) -> yaml.nodes.ScalarNode:
        event = self.peek_event()
        if not isinstance(event, yaml.events.ScalarEvent):
            raise PublishableTreeError("structured YAML scalar event is invalid")
        if len(event.value) > _MAX_YAML_SCALAR_CHARACTERS:
            raise PublishableTreeError(
                "structured YAML scalar exceeds decoded size limit"
            )
        if any(0xD800 <= ord(character) <= 0xDFFF for character in event.value):
            raise PublishableTreeError(
                "structured YAML scalar has an invalid codepoint"
            )
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
            raise PublishableTreeError(
                "structured YAML mapping key tag is unsupported"
            )
    except PublishableTreeError:
        raise
    except (KeyError, ValueError, IndexError) as error:
        raise PublishableTreeError(
            "structured YAML mapping key scalar is invalid"
        ) from error
    return tag, canonical


def _yaml_credential_assignment_values(value: str) -> tuple[str, ...]:
    if len(value) > _MAX_YAML_DOCUMENT_CHARACTERS:
        raise PublishableTreeError("structured YAML input exceeds size limit")
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
                    raise PublishableTreeError(
                        "structured YAML content exceeds depth limit"
                    )
                if identity in active:
                    raise PublishableTreeError(
                        "structured YAML recursive alias is invalid"
                    )
                visits += 1
                if visits > _MAX_YAML_NODES:
                    raise PublishableTreeError(
                        "structured YAML traversal exceeds node limit"
                    )
                active.add(identity)
                pending.append((node, depth, True))
                if isinstance(node, yaml.nodes.ScalarNode):
                    continue
                if isinstance(node, yaml.nodes.SequenceNode):
                    for child in reversed(node.value):
                        pending.append((child, depth + 1, False))
                    continue
                if not isinstance(node, yaml.nodes.MappingNode):
                    raise PublishableTreeError(
                        "structured YAML node kind is unsupported"
                    )
                seen_keys: set[tuple[str, str]] = set()
                for key_node, child in reversed(node.value):
                    if not isinstance(key_node, yaml.nodes.ScalarNode):
                        raise PublishableTreeError(
                            "structured YAML mapping key must be scalar"
                        )
                    key = key_node.value
                    if len(key) > 128:
                        raise PublishableTreeError(
                            "structured YAML key exceeds decoded size limit"
                        )
                    key_identity = _yaml_scalar_key_identity(loader, key_node)
                    if key_identity in seen_keys:
                        raise PublishableTreeError(
                            "structured YAML mapping key is duplicated"
                        )
                    seen_keys.add(key_identity)
                    if _is_sensitive_credential_name(key):
                        if not isinstance(child, yaml.nodes.ScalarNode):
                            raise PublishableTreeError(
                                "structured YAML sensitive value must be scalar"
                            )
                        candidates.append(child.value)
                    pending.append((child, depth + 1, False))
    except PublishableTreeError:
        raise
    except (yaml.YAMLError, UnicodeError, RecursionError, MemoryError) as error:
        raise PublishableTreeError("invalid structured YAML content") from error
    finally:
        loader.dispose()
    return tuple(candidates)


def contains_secret(
    value: str,
    *,
    python_source: bool = False,
    structured_suffix: str = "",
) -> bool:
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        return True
    candidates = list(_credential_assignment_values(value))
    if python_source:
        candidates.extend(_python_credential_assignment_values(value))
    if structured_suffix == ".json":
        candidates.extend(_json_credential_assignment_values(value))
    elif structured_suffix in {".yaml", ".yml"}:
        candidates.extend(_yaml_credential_assignment_values(value))
    return any(
        len(candidate) >= 40 and _shannon_entropy(candidate) >= 3.5
        for candidate in candidates
    )


def git_blob_oid(content: bytes) -> str:
    if not isinstance(content, bytes):
        raise PublishableTreeError("publishable content must be bytes")
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()  # noqa: S324 - Git object identity.


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(
        getattr(metadata, "st_file_attributes", 0)
        & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _canonical_path_violations(path: str) -> list[str]:
    if not isinstance(path, str) or not path:
        return ["invalid_path:<empty>"]
    violations: list[str] = []
    if unicodedata.normalize("NFC", path) != path:
        violations.append(f"non_nfc_path:{path}")
    if (
        "\\" in path
        or path.startswith(("/", "//"))
        or re.match(r"^[A-Za-z]:", path)
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
    ):
        violations.append(f"invalid_path:{path}")
        return violations
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        violations.append(f"traversal_path:{path}")
    if any(
        ":" in part
        or part.rstrip(" .") != part
        or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED
        for part in parts
    ):
        violations.append(f"unsafe_path_component:{path}")
    return violations


def _legacy_path(path: str) -> bool:
    return path.startswith(_LEGACY_PREFIXES) or path in _OBSOLETE_OPERATOR_PATHS


def _semantic_legacy_authority_references(text: str) -> tuple[str, ...]:
    found: set[str] = set()
    for match in re.finditer(r"(?:[\w.-]+[/\\])+(?:[\w.-]+)?", text):
        candidate = unicodedata.normalize("NFC", match.group(0)).casefold()
        candidate = candidate.replace("\\", "/")
        trailing_directory = candidate.endswith("/") or candidate.endswith("/.")
        components: list[str] = []
        for component in candidate.split("/"):
            if component in {"", "."}:
                continue
            if component == "..":
                if components:
                    components.pop()
                continue
            components.append(component)
        normalized = "/".join(components)
        if trailing_directory:
            normalized += "/"
        for legacy_reference in _LEGACY_PREFIXES:
            if normalized.startswith(legacy_reference):
                found.add(legacy_reference)
        for legacy_reference in _OBSOLETE_OPERATOR_PATHS:
            if normalized.rstrip(".") == legacy_reference:
                found.add(legacy_reference)
    return tuple(sorted(found))


def _allowed_path(path: str) -> bool:
    parts = path.split("/")
    if len(parts) == 1:
        return path in _ALLOWED_ROOT_FILES
    root = parts[0]
    if root not in _ALLOWED_DIRECTORY_ROOTS:
        return False
    if root == "docs":
        return len(parts) >= 3 and parts[1] in _ALLOWED_DOC_ROOTS
    return True


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        value,
    )
    return tuple(map(int, match.groups())) if match else None


def _placeholder_allowance(
    relative: str,
    line_number: int,
    *,
    source_todo_allowlist: Sequence[Mapping[str, Any]],
    version: str,
) -> tuple[bool, bool]:
    current = _version_tuple(version)
    for entry in source_todo_allowlist:
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
        or any(
            token in compact
            for token in ("apikey", "accesstoken", "clientsecret", "privatekey")
        )
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


def publishable_path_violations(relative: str) -> list[str]:
    """Classify publishability defects in one canonical relative path."""
    rows: list[str] = []
    parts = tuple(part for part in re.split(r"[/\\]", relative) if part)
    if _PRIVATE_NAMES.search(relative) or any(
        _runtime_evidence_component(part) for part in parts
    ):
        rows.append(f"private_runtime_evidence:{relative}")
    if any(_secret_like_component(part) for part in parts):
        rows.append(f"secret:{relative}")
    if _RESIDUE_COMPONENT.search(relative) or _RESIDUE_SUFFIX.search(relative):
        rows.append(f"residue:{relative}")
    return rows


def publishable_text_violations(
    relative: str,
    data: bytes,
    *,
    public_doc: bool,
    contains_secret_fn: Callable[..., bool] = contains_secret,
    source_todo_allowlist: Sequence[Mapping[str, Any]] | None = None,
    placeholder_reference_sha256: Mapping[
        str, Mapping[int, str]
    ] = EXACT_PLACEHOLDER_REFERENCE_SHA256,
    version: str = __version__,
) -> list[str]:
    """Classify publishability defects in one frozen file payload."""
    effective_allowlist = (
        SOURCE_TODO_ALLOWLIST
        if source_todo_allowlist is None
        else source_todo_allowlist
    )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raw_text = data.decode("latin-1")
        violations = [f"non_utf8_content:{relative}"]
        if _ABSOLUTE_USER_PATH.search(raw_text):
            violations.append(f"absolute_path:{relative}")
        if contains_secret_fn(raw_text):
            violations.append(f"secret:{relative}")
        return violations
    violations: list[str] = []
    if _ABSOLUTE_USER_PATH.search(text):
        violations.append(f"absolute_path:{relative}")
    if _PRIVATE_NAMES.search(relative):
        violations.append(f"private_runtime_evidence:{relative}")
    suffix = Path(relative).suffix.casefold()
    if public_doc and suffix == ".md" and not _legacy_path(relative):
        for legacy_reference in _semantic_legacy_authority_references(text):
            violations.append(
                f"legacy_authority_reference:{relative}:{legacy_reference}"
            )
    try:
        secret_found = contains_secret_fn(
            text,
            python_source=suffix in {".py", ".pyi"},
            structured_suffix=suffix,
        )
    except ValueError:
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
            if parts and re.fullmatch(
                r"hsconfig-[0-9]+(?:\.[0-9]+){2}", parts[0]
            ):
                reference_path = PurePosixPath(*parts[1:]).as_posix()
            elif reference_path.startswith("hsconfig/"):
                reference_path = "src/" + reference_path
        reference_digest = hashlib.sha256(line.strip().encode("utf-8")).hexdigest()
        if (
            placeholder_reference_sha256.get(reference_path, {}).get(line_number)
            == reference_digest
        ):
            continue
        if public_doc:
            violations.append(f"public_placeholder:{relative}:{line_number}")
            continue
        if Path(relative).suffix.casefold() in _ACTIVE_SOURCE_SUFFIXES:
            allowed, structurally_valid = _placeholder_allowance(
                relative,
                line_number,
                source_todo_allowlist=effective_allowlist,
                version=version,
            )
            if not allowed:
                reason = (
                    "expired_source_placeholder"
                    if structurally_valid
                    else "unallowlisted_source_placeholder"
                )
                violations.append(f"{reason}:{relative}:{line_number}")
    return violations


def _legacy_digest(rows: Sequence[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: str(item["path"]).encode("utf-8")):
        digest.update(str(row["git_mode"]).encode("ascii") + b"\0")
        digest.update(str(row["blob_oid"]).encode("ascii") + b"\0")
        digest.update(str(row["content_sha256"]).encode("ascii") + b"\0")
        digest.update(str(row["path"]).encode("utf-8") + b"\0")
    return digest.hexdigest()


def _normalize_row(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _ROW_FIELDS:
        raise PublishableTreeError("publishable inventory row schema mismatch")
    path = value["path"]
    git_mode = value["git_mode"]
    entry_kind = value["entry_kind"]
    tracked = value["tracked"]
    blob_oid = value["blob_oid"]
    content_sha256 = value["content_sha256"]
    content = value["content"]
    if (
        not isinstance(path, str)
        or not isinstance(git_mode, str)
        or not isinstance(entry_kind, str)
        or not isinstance(tracked, bool)
        or not isinstance(blob_oid, str)
        or _HEX40.fullmatch(blob_oid) is None
        or not isinstance(content_sha256, str)
        or _HEX64.fullmatch(content_sha256) is None
        or not isinstance(content, bytes)
        or len(content) > _MAX_FILE_BYTES
    ):
        raise PublishableTreeError("publishable inventory row schema mismatch")
    if hashlib.sha256(content).hexdigest() != content_sha256:
        raise PublishableTreeError("publishable inventory content digest mismatch")
    if git_blob_oid(content) != blob_oid:
        raise PublishableTreeError("publishable inventory Git blob identity mismatch")
    return dict(value)


def _markdown_anchor(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold().strip()
    normalized = re.sub(r"[`*_~]", "", normalized)
    normalized = re.sub(r"[^\w\- ]", "", normalized)
    normalized = re.sub(r"[\s-]+", "-", normalized).strip("-")
    return normalized


class _MarkdownScan(NamedTuple):
    visible_text: str
    targets: tuple[str, ...]
    undefined_references: tuple[str, ...]
    ambiguous_references: tuple[str, ...]
    headings: tuple[str, ...]
    work_units: int


def _normalize_markdown_reference(value: str) -> str:
    unescaped = re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])", r"\1", value)
    return re.sub(r"\s+", " ", html.unescape(unescaped).strip()).casefold()


def _markdown_destination(value: str) -> str:
    target = value.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    unescaped = re.sub(
        r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])",
        r"\1",
        target,
    )
    return html.unescape(unescaped)


class _MarkdownTokenizer:
    def __init__(self, text: str, *, operation_limit: int | None) -> None:
        if not isinstance(text, str):
            raise PublishableTreeError("markdown input must be text")
        default_limit = len(text) * _MARKDOWN_WORK_FACTOR + 1024
        if operation_limit is None:
            operation_limit = default_limit
        if type(operation_limit) is not int or operation_limit < 0:
            raise PublishableTreeError("markdown work budget is invalid")
        self.text = text
        self.limit = operation_limit
        self.work = 0
        self.characters = list(text)
        self.lines: list[tuple[int, int, int]] = []
        self.targets: list[str] = []
        self.headings: list[str] = []
        self.definitions: dict[str, str] = {}
        self.ambiguous: list[str] = []
        self.reference_uses: list[str] = []
        self._index_lines()
        self.list_content_indents = self._index_list_contexts()

    def _charge(self, units: int = 1) -> None:
        self.work += units
        if self.work > self.limit:
            raise PublishableTreeError("markdown work budget exceeded")

    def _index_lines(self) -> None:
        start = 0
        for index, character in enumerate(self.text):
            self._charge()
            if character != "\n":
                continue
            body_end = index - 1 if index > start and self.text[index - 1] == "\r" else index
            self.lines.append((start, body_end, index + 1))
            start = index + 1
        if start < len(self.text) or not self.lines:
            self.lines.append((start, len(self.text), len(self.text)))

    def run(self) -> _MarkdownScan:
        self._mask_code()
        visible = "".join(self.characters)
        self._charge(len(self.characters))
        self.visible = visible
        self._reject_raw_html_navigation()
        for start, end, _next_line in self.lines:
            content_start = self._block_content_start(start, end)
            heading = self._heading(content_start, end)
            if heading is not None:
                self.headings.append(heading)
        for content_start, end in self._inline_ranges():
            pairs = self._bracket_pairs(content_start, end)
            definition = self._reference_definition(content_start, end, pairs)
            if definition is not None:
                label, target = definition
                if not label or label in self.definitions:
                    self.ambiguous.append(label)
                else:
                    self.definitions[label] = target
                self.targets.append(target)
                continue
            self._scan_inline(content_start, end, pairs, images_only=False, depth=0)
        undefined: list[str] = []
        for reference in self.reference_uses:
            self._charge()
            target = self.definitions.get(reference)
            if target is None:
                undefined.append(reference)
            else:
                self.targets.append(target)
        return _MarkdownScan(
            visible_text=visible,
            targets=tuple(self.targets),
            undefined_references=tuple(undefined),
            ambiguous_references=tuple(self.ambiguous),
            headings=tuple(self.headings),
            work_units=self.work,
        )

    def _index_list_contexts(self) -> dict[int, int]:
        contexts: dict[int, int] = {}
        content_indents: list[int] = []
        for start, end, _next_line in self.lines:
            if all(self.text[index] in " \t" for index in range(start, end)):
                self._charge(end - start)
                continue
            leading, marker_content_indent = self._list_line_indents(start, end)
            if marker_content_indent is not None:
                while content_indents and leading < content_indents[-1]:
                    self._charge()
                    content_indents.pop()
                if len(content_indents) >= _MARKDOWN_MAX_DEPTH:
                    raise PublishableTreeError("markdown list nesting exceeds limit")
                content_indents.append(marker_content_indent)
                contexts[start] = marker_content_indent
                continue
            while content_indents and leading < content_indents[-1]:
                self._charge()
                content_indents.pop()
            if content_indents:
                contexts[start] = content_indents[-1]
        return contexts

    def _list_line_indents(self, start: int, end: int) -> tuple[int, int | None]:
        index = start
        columns = 0
        while index < end and self.text[index] in " \t":
            self._charge()
            columns = columns + 1 if self.text[index] == " " else (columns // 4 + 1) * 4
            index += 1
        marker_start = index
        if index < end and self.text[index] in "-+*":
            index += 1
        else:
            digits = 0
            while index < end and self.text[index].isdigit() and digits < 9:
                self._charge()
                index += 1
                digits += 1
            if digits == 0 or index >= end or self.text[index] not in ".)":
                return columns, None
            index += 1
        if index >= end or self.text[index] not in " \t":
            return columns, None
        marker_width = index - marker_start
        spacing_columns = 0
        while index < end and self.text[index] in " \t":
            self._charge()
            spacing_columns = (
                spacing_columns + 1
                if self.text[index] == " "
                else (spacing_columns // 4 + 1) * 4
            )
            index += 1
        return columns, columns + marker_width + max(1, spacing_columns)

    def _inline_ranges(self) -> tuple[tuple[int, int], ...]:
        ranges: list[tuple[int, int]] = []
        block_start: int | None = None
        block_end = 0
        blockquote_depth: int | None = None

        def flush() -> None:
            nonlocal block_start, block_end, blockquote_depth
            if block_start is not None:
                ranges.append((block_start, block_end))
            block_start = None
            block_end = 0
            blockquote_depth = None

        for start, end, _next_line in self.lines:
            content_start, line_blockquote_depth = self._raw_block_prefix(start, end)
            blank = True
            for index in range(content_start, end):
                self._charge()
                if self.visible[index] not in " \t":
                    blank = False
            if blank:
                flush()
                continue
            boundary = self._inline_block_boundary(start, end)
            if (
                block_start is not None
                and blockquote_depth
                and line_blockquote_depth < blockquote_depth
                and boundary in {None, "indented"}
            ):
                line_blockquote_depth = blockquote_depth
                if boundary == "indented":
                    boundary = None
            if block_start is not None and (
                line_blockquote_depth != blockquote_depth
                or boundary in {"container", "definition", "standalone"}
            ):
                flush()
            if boundary == "indented":
                if block_start is None:
                    continue
                boundary = None
            if block_start is None:
                block_start = content_start
                blockquote_depth = line_blockquote_depth
            block_end = end
            if boundary == "standalone":
                flush()
        flush()
        return tuple(ranges)

    def _reject_raw_html_navigation(self) -> None:
        index = 0
        end = len(self.visible)
        while index < end:
            self._charge()
            if self.visible[index] != "<":
                index += 1
                continue
            tag_end, forbidden = self._raw_html_tag(index, end)
            if forbidden:
                raise PublishableTreeError("markdown raw HTML navigation is forbidden")
            index = tag_end if tag_end is not None else index + 1

    def _raw_html_tag(self, start: int, end: int) -> tuple[int | None, bool]:
        index = start + 1
        if index < end and self.visible[index] == "/":
            index += 1
        name_start = index
        while index < end and (
            self.visible[index].isascii() and self.visible[index].isalnum()
            or self.visible[index] in "-_"
        ):
            self._charge()
            index += 1
        if index == name_start or (
            index < end and self.visible[index] not in _HTML5_SPACE + "/>"
        ):
            return None, False
        while index < end:
            while index < end and self.visible[index] in _HTML5_SPACE + "/":
                self._charge()
                index += 1
            if index >= end:
                return end, False
            if self.visible[index] == ">":
                return index + 1, False
            attribute_start = index
            while index < end and (
                self.visible[index].isascii()
                and (self.visible[index].isalnum() or self.visible[index] in "_:-.")
            ):
                self._charge()
                index += 1
            if index == attribute_start:
                index += 1
                continue
            attribute = self.visible[attribute_start:index].casefold()
            while index < end and self.visible[index] in _HTML5_SPACE:
                self._charge()
                index += 1
            if attribute.rsplit(":", 1)[-1] in {"href", "src"}:
                return end, True
            if index >= end or self.visible[index] != "=":
                continue
            index += 1
            while index < end and self.visible[index] in _HTML5_SPACE:
                self._charge()
                index += 1
            if index >= end:
                return end, False
            quote = self.visible[index] if self.visible[index] in "\"'" else None
            if quote is not None:
                index += 1
                while index < end and self.visible[index] != quote:
                    self._charge()
                    index += 1
                if index >= end:
                    return end, False
                index += 1
            else:
                while index < end and self.visible[index] not in _HTML5_SPACE + ">":
                    self._charge()
                    index += 1
        return end, False

    def _block_content_start(self, start: int, end: int) -> int:
        return self._raw_block_prefix(start, end)[0]

    def _raw_block_prefix(self, start: int, end: int) -> tuple[int, int]:
        index = start
        blockquote_depth = 0
        while index < end:
            spaces = 0
            while index < end and self.text[index] == " " and spaces < 3:
                self._charge()
                index += 1
                spaces += 1
            if index >= end or self.text[index] != ">":
                return index, blockquote_depth
            self._charge()
            index += 1
            blockquote_depth += 1
            if index < end and self.text[index] in " \t":
                self._charge()
                index += 1
        return index, blockquote_depth

    def _raw_block_content_start(self, start: int, end: int) -> int:
        return self._raw_block_prefix(start, end)[0]

    def _fence(self, start: int, end: int) -> tuple[str, int, int] | None:
        index = self._raw_block_content_start(start, end)
        if index >= end or self.text[index] not in "`~":
            return None
        character = self.text[index]
        run_end = index
        while run_end < end and self.text[run_end] == character:
            self._charge()
            run_end += 1
        if run_end - index < 3:
            return None
        return character, run_end - index, run_end

    def _mask_line(self, start: int, end: int) -> None:
        for index in range(start, end):
            self._charge()
            self.characters[index] = " "

    def _mask_blockquote_prefixes(self) -> None:
        for start, end, _next_line in self.lines:
            content_start, blockquote_depth = self._raw_block_prefix(start, end)
            if not blockquote_depth:
                continue
            self._mask_line(start, content_start)

    def _mask_code(self) -> None:
        fence_character: str | None = None
        fence_length = 0
        fence_blockquote_depth = 0
        for start, end, _next_line in self.lines:
            fence = self._fence(start, end)
            _content_start, blockquote_depth = self._raw_block_prefix(start, end)
            if fence_character is not None and (
                fence_blockquote_depth and blockquote_depth < fence_blockquote_depth
            ):
                fence_character = None
                fence_length = 0
                fence_blockquote_depth = 0
            if fence_character is not None:
                self._mask_line(start, end)
                if fence is None:
                    continue
                character, length, rest_start = fence
                rest_is_space = True
                for index in range(rest_start, end):
                    self._charge()
                    if self.text[index] not in " \t":
                        rest_is_space = False
                if character == fence_character and length >= fence_length and rest_is_space:
                    fence_character = None
                    fence_length = 0
                    fence_blockquote_depth = 0
                continue
            if fence is None:
                continue
            character, length, rest_start = fence
            if character == "`":
                invalid = False
                for index in range(rest_start, end):
                    self._charge()
                    if self.text[index] == "`":
                        invalid = True
                if invalid:
                    continue
            fence_character = character
            fence_length = length
            fence_blockquote_depth = blockquote_depth
            self._mask_line(start, end)

        self._mask_blockquote_prefixes()
        block_start: int | None = None
        blockquote_depth: int | None = None
        for start, end, next_line in self.lines:
            content_start, line_blockquote_depth = self._raw_block_prefix(start, end)
            blank = True
            for index in range(content_start, end):
                self._charge()
                if self.characters[index] not in " \t":
                    blank = False
            if blank:
                if block_start is not None:
                    self._mask_code_span_block(block_start, start)
                    block_start = None
                    blockquote_depth = None
            else:
                boundary = self._inline_block_boundary(start, end)
                if (
                    block_start is not None
                    and blockquote_depth
                    and line_blockquote_depth < blockquote_depth
                    and boundary in {None, "indented"}
                ):
                    line_blockquote_depth = blockquote_depth
                    if boundary == "indented":
                        boundary = None
                if block_start is not None and (
                    line_blockquote_depth != blockquote_depth
                    or (boundary is not None and boundary != "indented")
                ):
                    self._mask_code_span_block(block_start, start)
                    block_start = None
                    blockquote_depth = None
                if boundary == "indented" and block_start is None:
                    self._mask_line(start, end)
                    continue
                if boundary == "standalone":
                    self._mask_code_span_block(start, end)
                    continue
                if block_start is None:
                    block_start = start
                    blockquote_depth = line_blockquote_depth
            if next_line == len(self.text) and block_start is not None:
                self._mask_code_span_block(block_start, end)

    def _line_starts_atx_heading(self, start: int, end: int) -> bool:
        index = self._raw_block_content_start(start, end)
        if index >= end or self.characters[index] != "#":
            return False
        marker_end = index
        while marker_end < end and self.characters[marker_end] == "#":
            self._charge()
            marker_end += 1
        marker_length = marker_end - index
        return marker_length <= 6 and (
            marker_end == end or self.characters[marker_end] in " \t"
        )

    def _inline_block_boundary(self, start: int, end: int) -> str | None:
        index = self._raw_block_content_start(start, end)
        if index >= end:
            return None
        content = self.text[index:end]
        self._charge(len(content))
        if content.startswith((" ", "\t")):
            leading_columns = self._leading_columns(start, end)
            list_content_indent = self.list_content_indents.get(start)
            if (
                list_content_indent is None
                or leading_columns >= list_content_indent + 4
            ):
                return "indented"
        if self._line_starts_atx_heading(start, end):
            return "standalone"
        if _MARKDOWN_LIST_BLOCK_START.match(content):
            return "container"
        if _MARKDOWN_SETEXT_UNDERLINE.fullmatch(content):
            return "standalone"
        if self._is_thematic_break(content):
            return "standalone"
        if _MARKDOWN_REFERENCE_DEFINITION_START.match(content):
            return "definition"
        if self._starts_html_block(content):
            return "standalone"
        return None

    def _leading_columns(self, start: int, end: int) -> int:
        index = start
        columns = 0
        while index < end and self.text[index] in " \t":
            self._charge()
            columns = (
                columns + 1
                if self.text[index] == " "
                else (columns // 4 + 1) * 4
            )
            index += 1
        return columns

    @staticmethod
    def _is_thematic_break(content: str) -> bool:
        compact = content.replace(" ", "").replace("\t", "")
        return (
            len(compact) >= 3
            and compact[0] in "*-_"
            and all(character == compact[0] for character in compact)
        )

    @staticmethod
    def _starts_html_block(content: str) -> bool:
        if _MARKDOWN_RAW_TEXT_HTML_BLOCK.match(content):
            return True
        if (
            content.startswith("<!--")
            or content.startswith("<?")
            or content.startswith("<![CDATA[")
            or len(content) >= 3
            and content.startswith("<!")
            and content[2].isupper()
        ):
            return True
        tag = _MARKDOWN_HTML_BLOCK_TAG.match(content)
        if tag is not None and tag.group(1).casefold() in _MARKDOWN_HTML_BLOCK_TAGS:
            return True
        return _MARKDOWN_COMPLETE_HTML_TAG.fullmatch(content) is not None

    def _mask_code_span_block(self, start: int, end: int) -> None:
        stack: list[tuple[int, int, int]] = []
        by_length: dict[int, int] = {}
        intervals: list[tuple[int, int]] = []
        index = start
        while index < end:
            self._charge()
            if self.characters[index] == "\\" and index + 1 < end:
                index += 2
                self._charge()
                continue
            if self.characters[index] != "`":
                index += 1
                continue
            run_end = index + 1
            while run_end < end and self.characters[run_end] == "`":
                self._charge()
                run_end += 1
            length = run_end - index
            opener_index = by_length.get(length)
            if opener_index is None:
                by_length[length] = len(stack)
                stack.append((length, index, run_end))
            else:
                _length, opener, _opener_end = stack[opener_index]
                intervals.append((opener, run_end))
                for removed_length, _start, _end in stack[opener_index:]:
                    self._charge()
                    by_length.pop(removed_length, None)
                del stack[opener_index:]
            index = run_end
        if not intervals:
            return
        changes = [0] * (end - start + 1)
        for interval_start, interval_end in intervals:
            self._charge()
            changes[interval_start - start] += 1
            changes[interval_end - start] -= 1
        active = 0
        for offset in range(end - start):
            self._charge()
            active += changes[offset]
            index = start + offset
            if active and self.characters[index] not in "\r\n":
                self.characters[index] = " "

    def _bracket_pairs(self, start: int, end: int) -> dict[int, int]:
        stack: list[int] = []
        pairs: dict[int, int] = {}
        index = start
        while index < end:
            self._charge()
            character = self.visible[index]
            if character == "\\" and index + 1 < end:
                self._charge()
                index += 2
                continue
            if character == "[":
                if len(stack) >= _MARKDOWN_MAX_DEPTH:
                    raise PublishableTreeError("markdown nesting exceeds limit")
                stack.append(index)
            elif character == "]" and stack:
                pairs[stack.pop()] = index
            index += 1
        return pairs

    def _reference_definition(
        self,
        start: int,
        end: int,
        pairs: Mapping[int, int],
    ) -> tuple[str, str] | None:
        if start >= end or self.visible[start] != "[":
            return None
        label_end = pairs.get(start)
        if label_end is None or label_end + 1 >= end or self.visible[label_end + 1] != ":":
            return None
        index = label_end + 2
        while index < end and self.visible[index] in _MARKDOWN_LINK_WHITESPACE:
            self._charge()
            index += 1
        if index >= end:
            return None
        target_start = index
        if self.visible[index] == "<":
            index += 1
            while index < end and self.visible[index] != ">":
                self._charge()
                if self.visible[index] == "\\" and index + 1 < end:
                    index += 2
                else:
                    index += 1
            if index >= end:
                return None
            index += 1
        else:
            depth = 0
            while index < end and (
                self.visible[index] not in _MARKDOWN_LINK_WHITESPACE or depth
            ):
                self._charge()
                character = self.visible[index]
                if character == "\\" and index + 1 < end:
                    index += 2
                    continue
                if character == "(":
                    depth += 1
                    if depth > _MARKDOWN_MAX_DEPTH:
                        return None
                elif character == ")" and depth:
                    depth -= 1
                index += 1
            if depth:
                return None
        target = self.visible[target_start:index]
        if not self._reference_tail_is_valid(index, end):
            return None
        raw_label = self.visible[start + 1 : label_end]
        self._charge(len(raw_label) + len(target))
        return _normalize_markdown_reference(raw_label), _markdown_destination(target)

    def _reference_tail_is_valid(self, start: int, end: int) -> bool:
        index = start
        while index < end and self.visible[index] in _MARKDOWN_LINK_WHITESPACE:
            self._charge()
            index += 1
        if index == end:
            return True
        opener = self.visible[index]
        if opener not in {'"', "'", "("}:
            return False
        closer = ")" if opener == "(" else opener
        index += 1
        while index < end:
            self._charge()
            if self.visible[index] == "\\" and index + 1 < end:
                index += 2
                continue
            if self.visible[index] == closer:
                index += 1
                while index < end and self.visible[index] in _MARKDOWN_LINK_WHITESPACE:
                    self._charge()
                    index += 1
                return index == end
            index += 1
        return False

    def _heading(self, start: int, end: int) -> str | None:
        index = start
        while index < end and self.visible[index] == "#" and index - start < 6:
            self._charge()
            index += 1
        if index == start or index < end and self.visible[index] not in " \t":
            return None
        while index < end and self.visible[index] in " \t":
            self._charge()
            index += 1
        title = self.visible[index:end].strip()
        self._charge(end - index)
        title = re.sub(r"[ \t]+#+[ \t]*$", "", title).strip()
        return title

    def _scan_inline(
        self,
        start: int,
        end: int,
        pairs: Mapping[int, int],
        *,
        images_only: bool,
        depth: int,
    ) -> None:
        if depth > _MARKDOWN_MAX_DEPTH:
            raise PublishableTreeError("markdown nesting exceeds limit")
        index = start
        while index < end:
            self._charge()
            character = self.visible[index]
            if character == "\\" and index + 1 < end:
                self._charge()
                index += 2
                continue
            image = character == "!" and index + 1 < end and self.visible[index + 1] == "["
            opener = index + 1 if image else index
            if (character == "[" or image) and (not images_only or image):
                label_end = pairs.get(opener)
                if label_end is None:
                    index += 1
                    continue
                if not image:
                    self._scan_inline(
                        opener + 1,
                        label_end,
                        pairs,
                        images_only=True,
                        depth=depth + 1,
                    )
                raw_label = self.visible[opener + 1 : label_end]
                self._charge(len(raw_label))
                suffix = label_end + 1
                if suffix < end and self.visible[suffix] == "(":
                    target, consumed = self._inline_destination(suffix + 1, end)
                    if target is not None:
                        self.targets.append(_markdown_destination(target))
                        index = consumed
                        continue
                elif suffix < end and self.visible[suffix] == "[":
                    reference_end = pairs.get(suffix)
                    if reference_end is not None:
                        raw_reference = self.visible[suffix + 1 : reference_end]
                        self._charge(len(raw_reference))
                        reference = _normalize_markdown_reference(
                            raw_reference or raw_label
                        )
                        if reference:
                            self.reference_uses.append(reference)
                        index = reference_end + 1
                        continue
                else:
                    reference = _normalize_markdown_reference(raw_label)
                    if reference:
                        self.reference_uses.append(reference)
                    index = label_end + 1
                    continue
                index = label_end + 1
                continue
            if character == "<":
                consumed = self._autolink(index, end)
                if consumed is not None:
                    index = consumed
                    continue
            index += 1

    def _autolink(self, start: int, end: int) -> int | None:
        closing = start + 1
        while closing < end and self.text[closing] != ">":
            self._charge()
            if self.text[closing] in " \t<>" or ord(self.text[closing]) < 32:
                return None
            closing += 1
        if closing >= end:
            return None
        candidate = self.text[start + 1 : closing]
        self._charge(len(candidate))
        if _MARKDOWN_SCHEME_AUTOLINK.match(candidate):
            self.targets.append(_markdown_destination(candidate))
            return closing + 1
        if _MARKDOWN_EMAIL_AUTOLINK.fullmatch(candidate):
            self.targets.append(f"mailto:{candidate}")
            return closing + 1
        return None

    def _inline_destination(self, start: int, end: int) -> tuple[str | None, int]:
        index = start
        while index < end and self.visible[index] in _MARKDOWN_LINK_WHITESPACE:
            self._charge()
            index += 1
        if index >= end:
            return None, start
        if self.visible[index] == ")":
            return "", index + 1
        if self.visible[index] == "<":
            target_start = index
            index += 1
            while index < end and self.visible[index] != ">":
                self._charge()
                if self.visible[index] in "\r\n":
                    return None, start
                if self.visible[index] == "\\" and index + 1 < end:
                    index += 2
                else:
                    index += 1
            if index >= end:
                return None, start
            target = self.visible[target_start : index + 1]
            closing = self._inline_title_and_close(index + 1, end)
            return (target, closing) if closing is not None else (None, start)
        target_start = index
        depth = 0
        while index < end:
            self._charge()
            character = self.visible[index]
            if character == "\\" and index + 1 < end:
                index += 2
                continue
            if character == "(":
                depth += 1
                if depth > _MARKDOWN_MAX_DEPTH:
                    return None, start
                index += 1
                continue
            if character == ")":
                if depth == 0:
                    return self.visible[target_start:index], index + 1
                depth -= 1
                index += 1
                continue
            if character in _MARKDOWN_LINK_WHITESPACE and depth == 0:
                target = self.visible[target_start:index]
                closing = self._inline_title_and_close(index, end)
                return (target, closing) if closing is not None else (None, start)
            index += 1
        return None, start

    def _inline_title_and_close(self, start: int, end: int) -> int | None:
        index = start
        while index < end and self.visible[index] in _MARKDOWN_LINK_WHITESPACE:
            self._charge()
            index += 1
        if index < end and self.visible[index] == ")":
            return index + 1
        if index >= end or self.visible[index] not in {'"', "'", "("}:
            return None
        opener = self.visible[index]
        closer = ")" if opener == "(" else opener
        index += 1
        while index < end:
            self._charge()
            if self.visible[index] == "\\" and index + 1 < end:
                index += 2
                continue
            if self.visible[index] == closer:
                index += 1
                while index < end and self.visible[index] in _MARKDOWN_LINK_WHITESPACE:
                    self._charge()
                    index += 1
                return index + 1 if index < end and self.visible[index] == ")" else None
            index += 1
        return None


def _scan_markdown_document(
    text: str,
    *,
    operation_limit: int | None = None,
) -> _MarkdownScan:
    return _MarkdownTokenizer(text, operation_limit=operation_limit).run()


def _markdown_anchors(content: bytes) -> frozenset[str]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return frozenset()
    scan = _scan_markdown_document(text)
    return _markdown_heading_anchors(scan.headings)


def _markdown_heading_anchors(headings: Sequence[str]) -> frozenset[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for title in headings:
        base = _markdown_anchor(title)
        if not base:
            continue
        count = counts.get(base, 0)
        counts[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return frozenset(anchors)


def _markdown_targets(content: bytes) -> tuple[str, ...]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return ()
    return _scan_markdown_document(text).targets


def _markdown_link_violations(
    rows: Sequence[Mapping[str, object]],
    *,
    source_paths: frozenset[str] | None = None,
) -> list[str]:
    by_path = {str(row["path"]): row for row in rows}
    violations: list[str] = []
    scans: dict[str, _MarkdownScan] = {}
    anchors: dict[str, frozenset[str]] = {}
    for path, row in by_path.items():
        if Path(path).suffix.casefold() != ".md":
            continue
        try:
            text = row["content"].decode("utf-8")
        except UnicodeDecodeError:
            continue
        try:
            scan = _scan_markdown_document(text)
        except PublishableTreeError:
            if source_paths is None or path in source_paths:
                violations.append(f"markdown_parse_error:{path}")
            continue
        scans[path] = scan
        anchors[path] = _markdown_heading_anchors(scan.headings)
    for source, row in by_path.items():
        if (
            Path(source).suffix.casefold() != ".md"
            or source_paths is not None
            and source not in source_paths
        ):
            continue
        scan = scans.get(source)
        if scan is None:
            continue
        violations.extend(
            f"undefined_markdown_reference:{source}:{reference}"
            for reference in scan.undefined_references
        )
        violations.extend(
            f"ambiguous_markdown_reference:{source}:{reference}"
            for reference in scan.ambiguous_references
        )
        for raw_target in dict.fromkeys(scan.targets):
            target = raw_target
            try:
                split = urlsplit(target)
            except ValueError:
                violations.append(f"unsafe_markdown_link:{source}:{raw_target}")
                continue
            scheme = split.scheme.casefold()
            if scheme:
                if scheme not in {"https", "http", "mailto"}:
                    violations.append(f"unsafe_markdown_link:{source}:{raw_target}")
                continue
            if split.netloc or "\\" in target:
                violations.append(f"unsafe_markdown_link:{source}:{raw_target}")
                continue
            decoded_path = unquote(split.path)
            if any(ord(character) < 32 or ord(character) == 127 for character in decoded_path):
                violations.append(f"unsafe_markdown_link:{source}:{raw_target}")
                continue
            if decoded_path:
                if decoded_path.startswith("/"):
                    violations.append(f"unsafe_markdown_link:{source}:{raw_target}")
                    continue
                destination_parts = list(PurePosixPath(source).parent.parts)
                unsafe = False
                for part in decoded_path.split("/"):
                    if part in {"", "."}:
                        continue
                    if part == "..":
                        if not destination_parts:
                            unsafe = True
                            break
                        destination_parts.pop()
                    else:
                        destination_parts.append(part)
                if unsafe or not destination_parts:
                    violations.append(f"unsafe_markdown_link:{source}:{raw_target}")
                    continue
                destination = PurePosixPath(*destination_parts).as_posix()
            else:
                destination = source
            if _legacy_path(destination):
                violations.append(f"legacy_markdown_link:{source}:{raw_target}")
                continue
            if destination not in by_path:
                violations.append(f"unresolved_markdown_link:{source}:{raw_target}")
                continue
            fragment = unquote(split.fragment)
            if fragment and _markdown_anchor(fragment) not in anchors.get(destination, frozenset()):
                violations.append(f"unresolved_markdown_anchor:{source}:{raw_target}")
    return violations


def evaluate_publishable_tree(
    inventory: Sequence[Mapping[str, object]],
    *,
    mode: PublishableTreeMode,
    legacy_baseline: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Evaluate frozen rows without filesystem, Git, network, or subprocess I/O."""
    if mode not in {"working-pre-cutover", "candidate-index", "candidate", "final"}:
        raise PublishableTreeError("unsupported publishable-tree mode")
    if isinstance(inventory, (str, bytes, bytearray)) or not isinstance(inventory, Sequence):
        raise PublishableTreeError("publishable inventory must be a sequence")
    rows = tuple(_normalize_row(row) for row in inventory)
    paths = [str(row["path"]) for row in rows]
    if paths != sorted(paths, key=lambda value: value.encode("utf-8")):
        raise PublishableTreeError("publishable inventory must be path-byte-sorted")
    violations: list[str] = []
    seen: dict[str, str] = {}
    legacy_rows: list[Mapping[str, object]] = []
    active_rows: list[Mapping[str, object]] = []
    for row in rows:
        path = str(row["path"])
        violations.extend(_canonical_path_violations(path))
        folded = unicodedata.normalize("NFC", path).casefold()
        previous = seen.get(folded)
        if previous is not None:
            violations.append(f"casefold_duplicate:{previous}:{path}")
        else:
            seen[folded] = path
        if row["git_mode"] != "100644" or row["entry_kind"] != "regular":
            violations.append(f"non_regular:{path}")
        if mode != "working-pre-cutover" and row["tracked"] is not True:
            violations.append(f"untracked:{path}")
        if _legacy_path(path):
            legacy_rows.append(row)
            if mode != "working-pre-cutover":
                violations.append(f"legacy_path:{path}")
            continue
        active_rows.append(row)
        if not _allowed_path(path):
            violations.append(f"unexpected_root:{path}")

    legacy_digest = _legacy_digest(legacy_rows) if legacy_rows else None
    if mode == "working-pre-cutover":
        if legacy_baseline is None:
            if legacy_rows:
                violations.append("legacy_baseline_missing")
        elif (
            not isinstance(legacy_baseline, Mapping)
            or set(legacy_baseline) != _BASELINE_FIELDS
            or legacy_baseline.get("schema_version") != 1
            or not isinstance(legacy_baseline.get("count"), int)
            or isinstance(legacy_baseline.get("count"), bool)
            or not isinstance(legacy_baseline.get("aggregate_sha256"), str)
            or _HEX64.fullmatch(str(legacy_baseline.get("aggregate_sha256"))) is None
        ):
            raise PublishableTreeError("legacy baseline schema mismatch")
        elif legacy_rows and (
            len(legacy_rows) != legacy_baseline["count"]
            or legacy_digest != legacy_baseline["aggregate_sha256"]
        ):
            violations.append(
                "legacy_inventory_mismatch:"
                f"count={len(legacy_rows)}:sha256={legacy_digest or hashlib.sha256().hexdigest()}"
            )
    elif legacy_baseline is not None:
        violations.append("legacy_baseline_not_permitted")

    for row in active_rows:
        path = str(row["path"])
        content = row["content"]
        violations.extend(publishable_path_violations(path))
        public_doc = (
            path in {"README.md", "CONTRIBUTING.md", "SECURITY.md"}
            or path.startswith(("docs/architecture/", "docs/contracts/", "docs/operator/"))
            or Path(path).suffix.casefold() in {".md", ".rst", ".toml", ".yaml", ".yml"}
        )
        violations.extend(
            publishable_text_violations(
                path,
                content,
                public_doc=public_doc,
            )
        )
    violations.extend(
        _markdown_link_violations(
            rows,
            source_paths=frozenset(str(row["path"]) for row in active_rows),
        )
    )
    unique = sorted(set(violations))
    return {
        "schema_version": 1,
        "mode": mode,
        "passed": not unique,
        "violations": unique,
        "files_scanned": len(active_rows),
        "legacy_files_scanned": len(legacy_rows),
        "legacy_inventory_sha256": legacy_digest,
    }


def _clean_git_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.upper().startswith("GIT_"):
            environment.pop(key, None)
    if extra:
        environment.update(extra)
    return environment


def _git(
    repository: Path,
    *arguments: str,
    env: Mapping[str, str] | None = None,
    input_bytes: bytes | None = None,
) -> bytes:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            env=_clean_git_environment(env),
            input=input_bytes,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PublishableTreeError("Git inventory command failed") from exc
    if completed.returncode != 0 or completed.stderr:
        raise PublishableTreeError("Git inventory command failed")
    return completed.stdout


def _safe_regular_read(root: Path, relative: str) -> tuple[bytes, str]:
    parts = PurePosixPath(relative).parts
    candidate = root
    try:
        for part in parts[:-1]:
            candidate = candidate / part
            metadata = candidate.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or _is_reparse(metadata)
            ):
                return b"", "reparse" if _is_reparse(metadata) else "other"
        path = root.joinpath(*parts)
        before = path.lstat()
    except OSError:
        return b"", "missing"
    if stat.S_ISLNK(before.st_mode):
        return b"", "symlink"
    if _is_reparse(before):
        return b"", "reparse"
    if not stat.S_ISREG(before.st_mode) or getattr(before, "st_nlink", 1) not in {0, 1}:
        return b"", "other"
    if before.st_size > _MAX_FILE_BYTES:
        raise PublishableTreeError("publishable file exceeds size limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise PublishableTreeError("publishable file identity changed")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(1024 * 1024, _MAX_FILE_BYTES - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_FILE_BYTES:
                    raise PublishableTreeError("publishable file exceeds size limit")
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        path_after = path.lstat()
    except OSError as exc:
        raise PublishableTreeError("publishable file cannot be read safely") from exc
    def identity(row: os.stat_result) -> tuple[int, int, int, int, int, int]:
        return (
            row.st_dev,
            row.st_ino,
            row.st_size,
            row.st_mtime_ns,
            row.st_ctime_ns,
            row.st_mode,
        )
    if identity(before) != identity(opened) or identity(opened) != identity(after) or identity(before) != identity(path_after):
        raise PublishableTreeError("publishable file identity changed")
    return b"".join(chunks), "regular"


def _working_paths(repository: Path) -> tuple[tuple[str, str, str | None, bool], ...]:
    stage = _git(repository, "ls-files", "--stage", "-z")
    tracked: dict[str, tuple[str, str]] = {}
    for record in stage.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, oid, stage_number = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (UnicodeError, ValueError) as exc:
            raise PublishableTreeError("Git index inventory is invalid") from exc
        if stage_number != "0" or path in tracked:
            raise PublishableTreeError("Git index contains unresolved or duplicate entries")
        if _HEX40.fullmatch(oid) is None:
            raise PublishableTreeError("Git index inventory is invalid")
        tracked[path] = (mode, oid)
    raw_deleted = _git(repository, "ls-files", "--deleted", "-z")
    try:
        deleted = {
            value.decode("utf-8") for value in raw_deleted.split(b"\0") if value
        }
    except UnicodeDecodeError as exc:
        raise PublishableTreeError("Git deleted-path inventory is not UTF-8") from exc
    raw_paths = _git(
        repository,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    )
    try:
        paths = [
            path
            for value in raw_paths.split(b"\0")
            if value
            for path in (value.decode("utf-8"),)
            if path not in deleted
        ]
    except UnicodeDecodeError as exc:
        raise PublishableTreeError("Git path inventory is not UTF-8") from exc
    if len(paths) != len(set(paths)):
        raise PublishableTreeError("Git path inventory contains duplicates")
    return tuple(
        sorted(
            (
                (
                    path,
                    tracked[path][0] if path in tracked else "100644",
                    tracked[path][1] if path in tracked else None,
                    path in tracked,
                )
                for path in paths
            ),
            key=lambda row: row[0].encode("utf-8"),
        )
    )


def _candidate_index_rows(
    repository: Path,
    index_file: Path,
) -> tuple[tuple[str, str, bool, str, bytes, str], ...]:
    if not index_file.is_absolute():
        raise PublishableTreeError("candidate index path must be absolute")
    try:
        metadata = index_file.lstat()
    except OSError as exc:
        raise PublishableTreeError("candidate index is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or getattr(metadata, "st_nlink", 1) not in {0, 1}
    ):
        raise PublishableTreeError("candidate index is unsafe")
    env = {"GIT_INDEX_FILE": str(index_file)}
    raw = _git(repository, "ls-files", "--stage", "-z", env=env)
    rows: list[tuple[str, str, bool, str, bytes, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            fields, raw_path = record.split(b"\t", 1)
            mode, oid, stage_number = fields.decode("ascii").split()
            path = raw_path.decode("utf-8")
        except (UnicodeError, ValueError) as exc:
            raise PublishableTreeError("candidate index inventory is invalid") from exc
        if stage_number != "0" or _HEX40.fullmatch(oid) is None:
            raise PublishableTreeError("candidate index inventory is unresolved")
        content = _git(repository, "cat-file", "blob", oid)
        kind = "regular" if mode == "100644" else "symlink" if mode == "120000" else "gitlink" if mode == "160000" else "other"
        rows.append((path, mode, True, kind, content, oid))
    return tuple(sorted(rows, key=lambda row: row[0].encode("utf-8")))


def capture_publishable_inventory(
    root: Path,
    *,
    mode: PublishableTreeMode,
    index_file: Path | None = None,
    read_bytes: Callable[[str], bytes] | None = None,
) -> tuple[dict[str, object], ...]:
    """Capture one immutable normalized inventory for the pure evaluator."""
    if mode not in {"working-pre-cutover", "candidate-index", "candidate", "final"}:
        raise PublishableTreeError("unsupported publishable-tree mode")
    try:
        repository = Path(root).resolve(strict=True)
        metadata = repository.lstat()
    except (OSError, RuntimeError) as exc:
        raise PublishableTreeError("repository root is unavailable") from exc
    try:
        top_level = Path(
            _git(repository, "rev-parse", "--show-toplevel").decode("utf-8").strip()
        ).resolve(strict=True)
    except (OSError, RuntimeError, UnicodeError) as exc:
        raise PublishableTreeError("repository root is unsafe") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or top_level != repository
    ):
        raise PublishableTreeError("repository root is unsafe")
    rows: list[dict[str, object]] = []
    if mode == "candidate-index":
        if index_file is None:
            raise PublishableTreeError("candidate-index mode requires --index-file")
        candidates = _candidate_index_rows(repository, Path(index_file))
        for path, git_mode, tracked, kind, content, oid in candidates:
            rows.append(
                {
                    "path": path,
                    "git_mode": git_mode,
                    "entry_kind": kind,
                    "tracked": tracked,
                    "blob_oid": oid,
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                    "content": content,
                }
            )
    else:
        if index_file is not None:
            raise PublishableTreeError("--index-file is only valid in candidate-index mode")
        for path, git_mode, index_oid, tracked in _working_paths(repository):
            if read_bytes is None:
                content, kind = _safe_regular_read(repository, path)
            else:
                try:
                    content = read_bytes(path)
                except Exception as exc:
                    raise PublishableTreeError(f"tracked path cannot be read safely: {path}") from exc
                if not isinstance(content, bytes):
                    raise PublishableTreeError("publishable reader returned non-bytes")
                kind = "regular"
            canonical_content = content
            canonical_oid = git_blob_oid(canonical_content)
            if tracked and index_oid is not None and canonical_oid != index_oid:
                normalized = content.replace(b"\r\n", b"\n")
                if b"\r" not in normalized and git_blob_oid(normalized) == index_oid:
                    canonical_content = normalized
                    canonical_oid = index_oid
            rows.append(
                {
                    "path": path,
                    "git_mode": git_mode,
                    "entry_kind": kind,
                    "tracked": tracked,
                    "blob_oid": canonical_oid,
                    "content_sha256": hashlib.sha256(canonical_content).hexdigest(),
                    "content": canonical_content,
                }
            )
    return tuple(rows)


def evaluate_repository_tree(
    root: Path,
    *,
    mode: PublishableTreeMode,
    index_file: Path | None = None,
    read_bytes: Callable[[str], bytes] | None = None,
) -> dict[str, object]:
    inventory = capture_publishable_inventory(
        root,
        mode=mode,
        index_file=index_file,
        read_bytes=read_bytes,
    )
    baseline = WORKING_PRE_CUTOVER_LEGACY_BASELINE if mode == "working-pre-cutover" else None
    return evaluate_publishable_tree(
        inventory,
        mode=mode,
        legacy_baseline=baseline,
    )


__all__ = [
    "EXACT_PLACEHOLDER_REFERENCE_SHA256",
    "PublishableTreeError",
    "SOURCE_TODO_ALLOWLIST",
    "WORKING_PRE_CUTOVER_LEGACY_BASELINE",
    "capture_publishable_inventory",
    "contains_secret",
    "evaluate_publishable_tree",
    "evaluate_repository_tree",
    "git_blob_oid",
    "publishable_path_violations",
    "publishable_text_violations",
]
