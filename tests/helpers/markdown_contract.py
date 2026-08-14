from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import re


CANONICAL_PUBLIC_METADATA_SHA256 = {
    "LICENSE": "0b256a96f1b55a1cb4c6f33739ea7222d0fce2fa266882383e964fa466b435e5",
    "CONTRIBUTING.md": (
        "6353fd6263f5df815a26adb70f8f079e122b3e32419ceeb0ed271734e4980c8c"
    ),
    "SECURITY.md": (
        "24a05243b2e472ad59887d529faedd21a3dddb5a15050c03865a1e44ec1f7031"
    ),
    "README.md": (
        "4caabb0877281546e648ae73d4c47f2a000d671fc9cca1120ff5dd886ed2cfb6"
    ),
}


def normalized_utf8_sha256(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MarkdownToken:
    kind: str
    text: str
    raw: str
    line: int
    column: int
    target: str | None = None
    level: int | None = None


@dataclass(frozen=True)
class MarkdownError:
    reason: str
    line: int


@dataclass(frozen=True)
class MarkdownDocument:
    tokens: tuple[MarkdownToken, ...]
    errors: tuple[MarkdownError, ...]
    line_count: int

    @property
    def headings(self) -> tuple[MarkdownToken, ...]:
        return tuple(token for token in self.tokens if token.kind == "heading")

    @property
    def links(self) -> tuple[MarkdownToken, ...]:
        return tuple(token for token in self.tokens if token.kind == "link")

    def _lines(
        self,
        kinds: set[str],
        *,
        raw: bool,
        tombstone_kinds: set[str] | None = None,
    ) -> tuple[str, ...]:
        lines = [""] * self.line_count
        for token in self.tokens:
            if token.kind in kinds:
                value = token.raw if raw else token.text
                lines[token.line] += value
            elif tombstone_kinds is not None and token.kind in tombstone_kinds:
                lines[token.line] += "\ufffc"
        return tuple(lines)

    @property
    def policy_lines(self) -> tuple[str, ...]:
        return self._lines(
            {"heading", "link", "text"},
            raw=False,
            tombstone_kinds={"inline_code"},
        )

    @property
    def ordinary_text_lines(self) -> tuple[str, ...]:
        return self._lines(
            {"text"},
            raw=False,
            tombstone_kinds={"block_code", "heading", "inline_code", "link"},
        )

    @property
    def claim_lines(self) -> tuple[str, ...]:
        return self._lines(
            {"heading", "inline_code", "link", "text"},
            raw=False,
        )

    @property
    def prose_source_lines(self) -> tuple[str, ...]:
        return self._lines(
            {"heading", "inline_code", "link", "text"},
            raw=True,
        )

    @property
    def rendered_source_lines(self) -> tuple[str, ...]:
        return self._lines(
            {"block_code", "heading", "inline_code", "link", "text"},
            raw=True,
        )

    def _presentation_lines(self, kinds: set[str]) -> tuple[str, ...]:
        lines = [""] * self.line_count
        visible_tokens = [token for token in self.tokens if token.kind in kinds]
        for index, token in enumerate(visible_tokens):
            if token.kind in {"block_code", "inline_code"}:
                value = token.text
            else:
                value = _presentation_token_source(token)
                previous = visible_tokens[index - 1] if index else None
                following = (
                    visible_tokens[index + 1]
                    if index + 1 < len(visible_tokens)
                    else None
                )
                if (
                    following is not None
                    and following.line == token.line
                    and following.kind in {"inline_code", "link"}
                ):
                    value = re.sub(
                        r"(?<!\\)(?:\*{1,3}|_{1,3})$",
                        "",
                        value,
                    )
                if (
                    previous is not None
                    and previous.line == token.line
                    and previous.kind in {"inline_code", "link"}
                ):
                    value = re.sub(r"^(?:\*{1,3}|_{1,3})", "", value)
                value = _strip_inline_presentation(value)
            lines[token.line] += value
        return tuple(lines)

    @property
    def presentation_prose_lines(self) -> tuple[str, ...]:
        return self._presentation_lines(
            {"heading", "inline_code", "link", "text"}
        )

    @property
    def presentation_rendered_lines(self) -> tuple[str, ...]:
        return self._presentation_lines(
            {"block_code", "heading", "inline_code", "link", "text"}
        )

    @property
    def policy_text(self) -> str:
        return "\n".join(self.policy_lines)

    @property
    def prose_source(self) -> str:
        return "\n".join(self.prose_source_lines)

    @property
    def rendered_source(self) -> str:
        return "\n".join(self.rendered_source_lines)

    @property
    def presentation_prose(self) -> str:
        return "\n".join(self.presentation_prose_lines)


_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_ATX_HEADING = re.compile(r"^( {0,3})(#{1,6}) ([^\n]+?)\s*$")
_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_ANGLE_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_RAW_HTML = re.compile(r"^/?[A-Za-z][A-Za-z0-9-]*(?:\s|/|$)")
_RAW_HTML_TAG = re.compile(r"^(/?)([A-Za-z][A-Za-z0-9-]*)(?:\s|/|$)")
_RAW_TEXT_HTML_BLOCK = re.compile(
    r"^ {0,3}<(script|pre|style|textarea)(?:\s|>|$)",
    re.IGNORECASE,
)
_HTML_BLOCK_TAGS = frozenset(
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
_HTML_BLOCK_TAG = re.compile(
    r"^ {0,3}</?([A-Za-z][A-Za-z0-9-]*)(?:\s|/?>|$)",
    re.IGNORECASE,
)
_HTML_ATTRIBUTE_NAME = r"[A-Za-z_:][A-Za-z0-9_.:-]*"
_HTML_ATTRIBUTE_VALUE = r'(?:[^\s"\'=<>`]+|\'[^\']*\'|"[^"]*")'
_COMPLETE_HTML_TAG = re.compile(
    rf"^ {{0,3}}(?:"
    rf"<[A-Za-z][A-Za-z0-9-]*"
    rf"(?:\s+{_HTML_ATTRIBUTE_NAME}(?:\s*=\s*{_HTML_ATTRIBUTE_VALUE})?)*"
    rf"\s*/?>"
    rf"|</[A-Za-z][A-Za-z0-9-]*\s*>"
    rf")\s*$"
)
_VOID_HTML_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_GFM_ESCAPABLE = frozenset(r"!\"#$%&'()*+,-./:;<=>?@[\]^_`{|}~")
_BLOCKQUOTE_PREFIX = re.compile(r"^ {0,3}>[ \t]?")
_LIST_BLOCK_START = re.compile(r"^ {0,3}(?:[-+*]|\d{1,9}[.)])[ \t]+")
_BARE_URL = re.compile(r"(?:https?://|www\.)[^\s<>()]+", re.IGNORECASE)
_BARE_EMAIL = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?"
    r"(?:\.[A-Za-z0-9_]+)+"
)


def _run_length(text: str, start: int, character: str) -> int:
    end = start
    while end < len(text) and text[end] == character:
        end += 1
    return end - start


def _matching_backtick_run(text: str, start: int, length: int) -> int | None:
    cursor = start
    while cursor < len(text):
        marker = text.find("`", cursor)
        if marker < 0:
            return None
        run = _run_length(text, marker, "`")
        if run == length:
            return marker
        cursor = marker + run
    return None


def _closing_bracket_construct(text: str, start: int) -> int:
    label_end = text.find("]", start)
    if label_end < 0:
        return len(text)
    cursor = label_end + 1
    if cursor < len(text) and text[cursor] == "(":
        target_end = text.find(")", cursor + 1)
        return len(text) if target_end < 0 else target_end + 1
    if cursor < len(text) and text[cursor] == "[":
        reference_end = text.find("]", cursor + 1)
        return len(text) if reference_end < 0 else reference_end + 1
    return cursor


def _strip_blockquote_prefixes(line: str) -> tuple[str, bool]:
    stripped = line
    found = False
    while (prefix := _BLOCKQUOTE_PREFIX.match(stripped)) is not None:
        stripped = stripped[prefix.end() :]
        found = True
    return stripped, found


def _normalize_link_target(target: str) -> str | None:
    if not target or any(character.isspace() for character in target):
        return None
    starts_angle = target.startswith("<")
    ends_angle = target.endswith(">")
    if starts_angle or ends_angle:
        if not starts_angle or not ends_angle:
            return None
        target = target[1:-1]
        if not target or "<" in target or ">" in target:
            return None
        return target
    if "<" in target or ">" in target:
        return None
    return target


def _unescape_gfm(text: str) -> str:
    visible: list[str] = []
    cursor = 0
    while cursor < len(text):
        if (
            text[cursor] == "\\"
            and cursor + 1 < len(text)
            and text[cursor + 1] in _GFM_ESCAPABLE
        ):
            visible.append(text[cursor + 1])
            cursor += 2
            continue
        visible.append(text[cursor])
        cursor += 1
    return "".join(visible)


def _strip_inline_presentation(text: str) -> str:
    visible = re.sub(
        r"(?<![\\\w])(?:\*{1,3}|_{1,3})(?=\S)",
        "",
        text,
    )
    visible = re.sub(
        r"(?<=\S)(?<!\\)(?:\*{1,3}|_{1,3})(?!\w)",
        "",
        visible,
    )
    visible = _unescape_gfm(visible)
    return html.unescape(visible)


def _presentation_token_source(token: MarkdownToken) -> str:
    if token.kind == "text":
        return token.raw[:-1] if token.raw.endswith("\\") else token.raw
    if token.kind == "link":
        label_end = token.raw.find("]")
        return token.raw[1:label_end]
    if token.kind == "heading" and token.level is not None:
        atx_prefix = f"{'#' * token.level} "
        if token.raw.startswith(atx_prefix):
            return token.raw[len(atx_prefix) :]
        return token.raw
    return token.text


def _contains_unescaped_angle_bracket(text: str) -> bool:
    cursor = 0
    while cursor < len(text):
        if (
            text[cursor] == "\\"
            and cursor + 1 < len(text)
            and text[cursor + 1] in _GFM_ESCAPABLE
        ):
            cursor += 2
            continue
        if text[cursor] in "<>":
            return True
        cursor += 1
    return False


def _is_thematic_break(line: str) -> bool:
    content = line.lstrip(" ")
    if len(line) - len(content) > 3:
        return False
    compact = content.replace(" ", "").replace("\t", "")
    return len(compact) >= 3 and len(set(compact)) == 1 and compact[0] in "*-_"


def _valid_html_comment(
    source_lines: list[str],
    line_number: int,
    cursor: int,
) -> bool:
    remainder = "\n".join(
        [source_lines[line_number][cursor:], *source_lines[line_number + 1 :]]
    )
    content_start = len("<!--")
    content = remainder[content_start:]
    if content.startswith(">") or content.startswith("->"):
        return False
    closing = remainder.find("-->", content_start)
    if closing < 0:
        return True
    content = remainder[content_start:closing]
    return "--" not in content and not content.endswith("-")


def _html_block_start(
    source_lines: list[str],
    line_number: int,
) -> tuple[str, str] | None:
    line = source_lines[line_number]
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return None

    raw_text = _RAW_TEXT_HTML_BLOCK.match(line)
    if raw_text is not None:
        return "raw_text", raw_text.group(1).lower()
    if stripped.startswith("<!--"):
        if _valid_html_comment(source_lines, line_number, len(line) - len(stripped)):
            return "comment", "-->"
        return "invalid_comment", ""
    if stripped.startswith("<?"):
        return "terminator", "?>"
    if stripped.startswith("<![CDATA["):
        return "terminator", "]]>"
    if re.match(r"<![A-Z]", stripped):
        return "terminator", ">"

    block_tag = _HTML_BLOCK_TAG.match(line)
    if block_tag is not None and block_tag.group(1).lower() in _HTML_BLOCK_TAGS:
        return "blank", ""
    if _COMPLETE_HTML_TAG.fullmatch(line) is not None:
        return "blank", ""
    return None


def _html_block_closes(mode: str, terminator: str, line: str) -> bool:
    if mode == "raw_text":
        return re.search(rf"</{re.escape(terminator)}\s*>", line, re.IGNORECASE) is not None
    return terminator in line


def _visible_link_label(label: str) -> str | None:
    visible: list[str] = []
    cursor = 0
    while cursor < len(label):
        if label[cursor] != "`":
            if label[cursor] in "[]~":
                return None
            if (
                label[cursor] == "\\"
                and cursor + 1 < len(label)
                and label[cursor + 1] in _GFM_ESCAPABLE
            ):
                visible.append(label[cursor + 1])
                cursor += 2
                continue
            visible.append(label[cursor])
            cursor += 1
            continue
        run = _run_length(label, cursor, "`")
        closing = _matching_backtick_run(label, cursor + run, run)
        if closing is None:
            return None
        visible.append(label[cursor + run : closing])
        cursor = closing + run
    return "".join(visible)


def scan_markdown(text: str) -> MarkdownDocument:
    source_lines = text.splitlines()
    normalized_source_lines = [
        _strip_blockquote_prefixes(line)[0] for line in source_lines
    ]
    tokens: list[MarkdownToken] = []
    errors: list[MarkdownError] = []
    fence: tuple[str, int, bool] | None = None
    html_block: tuple[str, str, bool] | None = None
    inline_html_tag: str | None = None
    inline_html_terminator: str | None = None
    comment_open = False
    inline_code_run: int | None = None
    inline_code_start_line: int | None = None

    def add_error(reason: str, line: int) -> None:
        if not any(item.reason == reason and item.line == line for item in errors):
            errors.append(MarkdownError(reason=reason, line=line))

    for line_number, source_line in enumerate(source_lines):
        if fence is not None:
            character, minimum, in_blockquote = fence
            if in_blockquote:
                line, blockquoted = _strip_blockquote_prefixes(source_line)
                if blockquoted:
                    add_error("blockquote", line_number)
            else:
                line = source_line
            if re.fullmatch(
                rf" {{0,3}}{re.escape(character)}{{{minimum},}}\s*",
                line,
            ):
                fence = None
            else:
                tokens.append(
                    MarkdownToken(
                        kind="block_code",
                        text=line,
                        raw=line,
                        line=line_number,
                        column=0,
                    )
                )
            continue

        if html_block is not None:
            mode, terminator, in_blockquote = html_block
            if in_blockquote:
                line, blockquoted = _strip_blockquote_prefixes(source_line)
                if blockquoted:
                    add_error("blockquote", line_number)
            else:
                line = source_line
            if mode == "blank":
                if not line.strip():
                    html_block = None
                continue
            if _html_block_closes(mode, terminator, line):
                html_block = None
            continue

        line, blockquoted = _strip_blockquote_prefixes(source_line)
        if blockquoted:
            add_error("blockquote", line_number)

        html_sources = normalized_source_lines if blockquoted else source_lines
        setext = _SETEXT_UNDERLINE.fullmatch(line)
        previous_line_tokens = [
            token for token in tokens if token.line == line_number - 1
        ]
        setext_candidate = setext is not None and bool(previous_line_tokens) and all(
            token.kind in {"inline_code", "link", "text"}
            for token in previous_line_tokens
        )
        thematic_break = _is_thematic_break(line)
        starts_new_block = (
            not line.strip()
            or _FENCE_OPEN.match(line) is not None
            or line.startswith("\t")
            or line.startswith("    ")
            or _ATX_HEADING.fullmatch(line) is not None
            or _LIST_BLOCK_START.match(line) is not None
            or re.match(r"^ {0,3}\[", line) is not None
            or _html_block_start(html_sources, line_number) is not None
            or blockquoted
            or setext_candidate
            or thematic_break
        )
        if inline_code_run is not None and starts_new_block:
            add_error(
                "unclosed_code_span",
                inline_code_start_line
                if inline_code_start_line is not None
                else line_number,
            )
            inline_code_run = None
            inline_code_start_line = None

        if setext_candidate:
            if any(token.kind != "text" for token in previous_line_tokens):
                add_error("setext_non_text_child", line_number)
                continue
            first = previous_line_tokens[0]
            del tokens[-len(previous_line_tokens) :]
            tokens.append(
                MarkdownToken(
                    kind="heading",
                    text="".join(token.text for token in previous_line_tokens),
                    raw="".join(token.raw for token in previous_line_tokens),
                    line=line_number - 1,
                    column=first.column,
                    level=1 if setext is not None and setext.group(1)[0] == "=" else 2,
                )
            )
            continue
        if thematic_break:
            continue

        if (
            inline_code_run is None
            and not comment_open
            and inline_html_tag is None
            and inline_html_terminator is None
        ):
            opening = _FENCE_OPEN.match(line)
            if opening is not None:
                marker = opening.group(1)
                info_string = line[opening.end() :]
                if marker[0] == "`" and "`" in info_string:
                    add_error("ambiguous_fence", line_number)
                    continue
                fence = (marker[0], len(marker), blockquoted)
                continue
            if line.startswith("\t") or line.startswith("    "):
                code = line[1:] if line.startswith("\t") else line[4:]
                tokens.append(
                    MarkdownToken(
                        kind="block_code",
                        text=code,
                        raw=code,
                        line=line_number,
                        column=0,
                    )
                )
                continue
            html_start = _html_block_start(html_sources, line_number)
            if html_start is not None:
                mode, terminator = html_start
                add_error("raw_html", line_number)
                if mode == "invalid_comment":
                    continue
                if mode == "blank":
                    html_block = (mode, terminator, blockquoted)
                elif not _html_block_closes(mode, terminator, line):
                    html_block = (mode, terminator, blockquoted)
                continue

        line_token_start = len(tokens)
        cursor = 0
        while cursor < len(line):
            if inline_html_terminator is not None:
                closing = line.find(inline_html_terminator, cursor)
                if closing < 0:
                    cursor = len(line)
                    continue
                cursor = closing + len(inline_html_terminator)
                inline_html_terminator = None
                continue

            if inline_html_tag is not None:
                closing_tag = re.search(
                    rf"</{re.escape(inline_html_tag)}\s*>",
                    line[cursor:],
                    re.IGNORECASE,
                )
                if closing_tag is None:
                    cursor = len(line)
                    continue
                cursor += closing_tag.end()
                inline_html_tag = None
                continue

            if inline_code_run is not None:
                closing = _matching_backtick_run(line, cursor, inline_code_run)
                if closing is None:
                    tokens.append(
                        MarkdownToken(
                            kind="inline_code",
                            text=line[cursor:],
                            raw=line[cursor:],
                            line=line_number,
                            column=cursor,
                        )
                    )
                    cursor = len(line)
                    continue
                tokens.append(
                    MarkdownToken(
                        kind="inline_code",
                        text=line[cursor:closing],
                        raw=line[cursor : closing + inline_code_run],
                        line=line_number,
                        column=cursor,
                    )
                )
                cursor = closing + inline_code_run
                inline_code_run = None
                inline_code_start_line = None
                continue

            if comment_open:
                closing = line.find("-->", cursor)
                if closing < 0:
                    cursor = len(line)
                    continue
                cursor = closing + 3
                comment_open = False
                continue

            if line.startswith("<!--", cursor):
                add_error("raw_html", line_number)
                if not _valid_html_comment(html_sources, line_number, cursor):
                    cursor += 4
                    continue
                comment_open = True
                cursor += 4
                continue

            inline_html_marker = next(
                (
                    (opener, terminator)
                    for opener, terminator in (
                        ("<?", "?>"),
                        ("<![CDATA[", "]]>"),
                        ("<!", ">"),
                    )
                    if line.startswith(opener, cursor)
                ),
                None,
            )
            if inline_html_marker is not None:
                opener, terminator = inline_html_marker
                add_error("raw_html", line_number)
                closing = line.find(terminator, cursor + len(opener))
                if closing < 0:
                    inline_html_terminator = terminator
                    cursor = len(line)
                else:
                    cursor = closing + len(terminator)
                continue

            character = line[cursor]
            if character == "`":
                run = _run_length(line, cursor, "`")
                closing = _matching_backtick_run(line, cursor + run, run)
                if closing is None:
                    tokens.append(
                        MarkdownToken(
                            kind="inline_code",
                            text=line[cursor + run :],
                            raw=line[cursor:],
                            line=line_number,
                            column=cursor,
                        )
                    )
                    inline_code_run = run
                    inline_code_start_line = line_number
                    cursor = len(line)
                    continue
                tokens.append(
                    MarkdownToken(
                        kind="inline_code",
                        text=line[cursor + run : closing],
                        raw=line[cursor : closing + run],
                        line=line_number,
                        column=cursor,
                    )
                )
                cursor = closing + run
                continue

            if line.startswith("~~", cursor):
                add_error("strikethrough", line_number)
                closing = line.find("~~", cursor + 2)
                cursor = len(line) if closing < 0 else closing + 2
                continue

            if line.startswith("![", cursor):
                add_error("image", line_number)
                cursor = _closing_bracket_construct(line, cursor + 2)
                continue

            if line.startswith(r"\[", cursor):
                add_error("escaped_link", line_number)
                cursor = _closing_bracket_construct(line, cursor + 2)
                continue

            if character == "[":
                label_end = line.find("]", cursor + 1)
                if label_end < 0:
                    add_error("malformed_link", line_number)
                    cursor = len(line)
                    continue
                label = line[cursor + 1 : label_end]
                after_label = label_end + 1
                if after_label < len(line) and line[after_label] == "(":
                    target_end = line.find(")", after_label + 1)
                    if target_end < 0:
                        add_error("malformed_link", line_number)
                        cursor = len(line)
                        continue
                    target = line[after_label + 1 : target_end]
                    normalized_target = _normalize_link_target(target)
                    if "`" in label:
                        add_error("inline_code_in_link_label", line_number)
                        cursor = target_end + 1
                        continue
                    if _contains_unescaped_angle_bracket(label):
                        add_error("raw_html_in_link_label", line_number)
                        cursor = target_end + 1
                        continue
                    visible_label = _visible_link_label(label)
                    if (
                        not visible_label
                        or normalized_target is None
                    ):
                        add_error("unsupported_link", line_number)
                        cursor = target_end + 1
                        continue
                    raw = line[cursor : target_end + 1]
                    tokens.append(
                        MarkdownToken(
                            kind="link",
                            text=visible_label,
                            raw=raw,
                            line=line_number,
                            column=cursor,
                            target=normalized_target,
                        )
                    )
                    cursor = target_end + 1
                    continue
                add_error("reference_link", line_number)
                tokens.append(
                    MarkdownToken(
                        kind="text",
                        text=label,
                        raw=label,
                        line=line_number,
                        column=cursor,
                    )
                )
                cursor = _closing_bracket_construct(line, cursor + 1)
                continue

            if character == "<":
                closing = line.find(">", cursor + 1)
                if closing >= 0:
                    body = line[cursor + 1 : closing]
                    if _ANGLE_SCHEME.match(body) or (
                        "@" in body and not any(item.isspace() for item in body)
                    ):
                        add_error("angle_autolink", line_number)
                        cursor = closing + 1
                        continue
                    if _RAW_HTML.match(body):
                        add_error("raw_html", line_number)
                        tag = _RAW_HTML_TAG.match(body)
                        cursor = closing + 1
                        if tag is not None:
                            is_closing = bool(tag.group(1))
                            name = tag.group(2).lower()
                            is_self_closing = body.rstrip().endswith("/")
                            if (
                                not is_closing
                                and not is_self_closing
                                and name not in _VOID_HTML_TAGS
                            ):
                                inline_html_tag = name
                        continue

            next_special = min(
                (
                    position
                    for marker in ("`", "~~", "![", r"\[", "[", "<", "<!--")
                    if (position := line.find(marker, cursor + 1)) >= 0
                ),
                default=len(line),
            )
            raw = line[cursor:next_special]
            visible = raw
            if next_special == len(line) and visible.endswith("\\"):
                visible = visible[:-1]
            visible = _unescape_gfm(visible)
            tokens.append(
                MarkdownToken(
                    kind="text",
                    text=visible,
                    raw=raw,
                    line=line_number,
                    column=cursor,
                )
            )
            cursor = next_special

        line_tokens = tokens[line_token_start:]
        visible_raw = "".join(token.raw for token in line_tokens)
        heading = _ATX_HEADING.fullmatch(visible_raw)
        if heading is not None and all(
            token.kind == "text" for token in line_tokens
        ):
            del tokens[line_token_start:]
            hashes = heading.group(2)
            heading_source = heading.group(3)
            heading_text = _unescape_gfm(heading_source)
            tokens.append(
                MarkdownToken(
                    kind="heading",
                    text=heading_text,
                    raw=f"{hashes} {heading_source}",
                    line=line_number,
                    column=len(heading.group(1)),
                    level=len(hashes),
                )
            )

        visible_for_autolinks = "".join(
            token.text
            for token in tokens[line_token_start:]
            if token.kind in {"heading", "text"}
        )
        if _BARE_URL.search(visible_for_autolinks):
            add_error("bare_url", line_number)
        if _BARE_EMAIL.search(visible_for_autolinks):
            add_error("bare_email", line_number)

    eof_line = max(len(source_lines) - 1, 0)
    if comment_open:
        add_error("unclosed_html_comment", eof_line)
    if html_block is not None and html_block[0] == "comment":
        add_error("unclosed_html_comment", eof_line)
    if fence is not None:
        add_error("unclosed_fence", eof_line)
    if inline_code_run is not None:
        add_error(
            "unclosed_code_span",
            inline_code_start_line
            if inline_code_start_line is not None
            else eof_line,
        )
    return MarkdownDocument(
        tokens=tuple(tokens),
        errors=tuple(errors),
        line_count=len(source_lines),
    )
