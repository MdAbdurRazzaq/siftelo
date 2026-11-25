"""Conservative parser for Markdown handoff documents.

The parser extracts only *explicit* markers. It never infers test outcomes
from prose. Recognised markers:

* Metadata lines (case-insensitive), e.g. ``Branch: main`` / ``HEAD: 3f2a...``
  or ``Commit: 3f2a...``. Only hex strings of 7-40 characters are accepted.
* Relative Markdown links ``[label](relative/path)`` and backticked paths in
  an ``## Evidence`` section. Absolute URLs and anchors are ignored.
* Lines starting with ``Pending approval:`` are recorded as pending approvals.
* Lines starting with ``Blocked:`` or ``Blocker:`` (optionally after a list
  bullet, an ordered marker or a blockquote marker, with a non-empty reason) are
  recorded as author-reported blockers. Matching is case-sensitive and anchored
  to the start of the line, so prose such as "the release was blocked by CI" is
  never a blocker. Headings are not markers. Blockers are never treated as
  resolved or verified.
* A task-list item (``- [ ]``, ``1. [ ]``) carrying one of those markers is
  read the same way: unchecked means unresolved.
* A checked task (``- [x]`` or ``- [X]``) carrying a marker is not an active
  blocker or pending approval. It is recorded as a checked item, so the report
  can surface it for review. A checked item is not treated as resolved.
* Lines that claim tests passed are recorded as *claims*. They are never
  treated as verified; the checker reports them as ``agent_reported``.

Code is not prose. Before any extraction, every line is classified (see
``_scan_blocks``) as blank, text, fence or indented code. Only text lines are
read, so a marker, a heading, a link or a recorded value inside a fenced block
or a four-space-indented code block is an example and is ignored. This holds
inside blockquotes too: a fence inside ``>`` is code for its own quote. A fence
that is never closed hides the lines after it, and the parser then records a
warning.

Line endings follow Markdown: a line ends at LF, CR or CRLF only. Other Unicode
separators are ordinary characters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_HANDOFF_BYTES = 1024 * 1024
MAX_REFERENCES = 500

# Optional container prefixes that a renderer shows as a list item or a blockquote.
_CONTAINER = r"^[ \t]*(?:>[ \t]*)*"
# An optional list marker and, for blockers, an optional task checkbox after it.
_BLOCKER_ITEM = r"(?:(?:[-*+]|\d{1,9}[.)])[ \t]+(?:\[(?P<box>[ xX])\][ \t]+)?)?"
_APPROVAL_ITEM = r"(?:(?:[-*+]|\d{1,9}[.)])\s*(?:\[(?P<box>[ xX])\]\s+)?)?"
_META_RE = re.compile(_CONTAINER + r"(?:(?:[-*+]|\d{1,9}[.)])\s*)?(?P<key>branch|head|commit|sha)\s*:\s*"
                      r"(?P<value>[^\s`]+)", re.I)
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.I)
_LINK_RE = re.compile(r"\[(?P<label>[^\]]*)\]\((?P<target>[^)\s]+)\)")
_CODE_PATH_RE = re.compile(r"`(?P<path>[^`\s]+)`")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*$")
_APPROVAL_RE = re.compile(_CONTAINER + _APPROVAL_ITEM + r"Pending approval\s*:\s*"
                          r"(?P<text>.+?)\s*$", re.I)
# Deliberately narrow: exact, capitalised markers at the start of a line, with a non-empty reason.
_BLOCKER_RE = re.compile(_CONTAINER + _BLOCKER_ITEM + r"(?:Blocked|Blocker):\s*"
                         r"(?P<text>\S.*?)\s*$")
# A fence opens with three or more backticks or tildes and closes with the same character,
# at least as many of them, and nothing else on the line (CommonMark rules, simplified).
# Only spaces and tabs count as indentation; other Unicode spaces are text.
_FENCE_RE = re.compile(r"^[ \t]*(?P<run>`{3,}|~{3,})(?P<info>.*)$")
# A list item: optional leading spaces, a bullet or ordered marker, then a gap and the content.
_LIST_ITEM_RE = re.compile(r"^(?P<lead>[ \t]*)(?P<marker>[-*+]|\d{1,9}[.)])(?P<gap>[ \t]*)(?P<rest>.*)$")
_THEMATIC_BREAK_RE = re.compile(r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
# One level of blockquote marker: up to three spaces, ">", and one optional space.
_QUOTE_MARK_RE = re.compile(r"^[ \t]{0,3}>[ \t]?")
_TEST_CLAIM_RE = re.compile(
    r"\b(tests?|test suite|specs?|checks?|ci)\b[^.\n]{0,40}\b(pass(ed|ing)?|green|succeeded|all good)\b"
    r"|\ball tests (pass|passed)\b",
    re.I,
)
_PUBLICATION_RE = re.compile(r"\b(publish|publication|push|release|post)\w*\b", re.I)
# Markdown line endings: LF, CR or CRLF. Nothing else ends a line.
_LINE_END_RE = re.compile(r"\r\n|\r|\n")

# Line kinds produced by _scan_blocks. Only TEXT lines are read for content.
BLANK = "blank"
TEXT = "text"
FENCE = "fence"
CODE = "code"


@dataclass
class Reference:
    kind: str  # "link" | "evidence_path"
    target: str
    line: int


@dataclass
class TestClaim:
    line: int
    text: str


@dataclass
class PendingApproval:
    line: int
    text: str


@dataclass
class Blocker:
    line: int
    text: str  # the author's own words, never interpreted


@dataclass
class CheckedItem:
    """A checked task carrying a marker. Recorded for review; never active, never resolved."""

    line: int
    kind: str  # "blocker" | "approval"
    text: str


@dataclass
class HandoffDocument:
    path_label: str
    branch: str | None = None
    branch_line: int | None = None  # line of the first accepted Branch: value
    head: str | None = None
    head_line: int | None = None  # line of the first accepted HEAD/commit value
    metadata_lines: list[int] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    test_claims: list[TestClaim] = field(default_factory=list)
    pending_approvals: list[PendingApproval] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)
    checked_items: list[CheckedItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def is_url(target: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target)) or target.startswith("#")


def _indent(line: str) -> int:
    """Width of the leading spaces and tabs, with tabs expanded to four-column stops."""
    width = 0
    for ch in line:
        if ch == " ":
            width += 1
        elif ch == "\t":
            width += 4 - width % 4
        else:
            break
    return width


def _quote_split(line: str, limit: int | None = None) -> tuple[int, str]:
    """Remove up to `limit` levels of blockquote marker. Return (levels removed, remaining text)."""
    depth = 0
    text = line
    while limit is None or depth < limit:
        match = _QUOTE_MARK_RE.match(text)
        if match is None:
            break
        text = text[match.end():]
        depth += 1
    return depth, text


def _list_item_content(raw: str) -> int | None:
    """Column where a list item's content starts, or None when the line is not a list item.

    ``-x`` is not an item (no gap after the marker). A marker with more than four
    spaces after it has content starting one column after the marker, as CommonMark does.
    """
    match = _LIST_ITEM_RE.match(raw)
    if not match:
        return None
    gap, rest = match.group("gap"), match.group("rest")
    if gap == "" and rest.strip(" \t"):
        return None
    width = len(gap) if 1 <= len(gap) <= 4 and rest.strip(" \t") else 1
    return _indent(raw) + len(match.group("marker")) + width


def _fence_info_ok(match: re.Match) -> bool:
    """A backtick fence's info string may not contain a backtick (CommonMark)."""
    return not ("`" in match.group("info") and match.group("run")[0] == "`")


def _scan_blocks(lines: list[str]) -> tuple[list[str], int | None]:
    """Classify each line as blank, text, fence (markers and body) or code (indented code).

    Rules, simplified from CommonMark for the constructs a handoff uses. Columns are
    measured from the left edge, or from the content column of the innermost list item.

    * Blockquote markers are removed before classification. A change of quote depth
      ends any open list item or indented code block. A fence opened inside a quote
      is held by that quote: a line with fewer markers ends it, and its body keeps
      the quote's own markers removed. A fence at top level keeps every character of
      the line, including any ``>``.
    * A list item opens a list context whose content column is the column after its
      marker and gap. A non-blank line indented less than that column ends the context,
      unless it continues a paragraph lazily. A thematic break, a heading or a fence
      never continues lazily, and a thematic break always ends the context.
    * Indented code starts with a line indented four or more columns, relative to the
      list context, that does not continue a paragraph. It continues while lines stay
      indented four or more, and blank lines do not end it.
    * A fence opens with three or more backticks or tildes at a relative indentation of
      up to three columns, or on a list-item line at the item's content. It closes with
      the same character, at least as long, with no info string other than spaces and
      tabs, and at a relative indentation of up to three. A fence inside a list item
      ends when the item ends, which is the first non-blank line less indented than the
      item's content column. An unclosed fence otherwise runs to the end of the file.

    Returns the kinds and, when a fence is still open at the end, the 1-based line that
    opened it. Otherwise the second value is None.
    """
    kinds: list[str] = []
    fence: tuple[str, int, int] | None = None  # (fence character, run length, base column)
    fence_quote = 0  # blockquote depth that holds the open fence (0 = top level)
    fence_line: int | None = None
    list_base: int | None = None  # content column of the innermost open list item
    code_base: int | None = None  # base column of an open indented code block
    paragraph_open = False  # the previous non-blank line was paragraph text
    prev_kind = BLANK
    prev_depth = 0

    for number, raw in enumerate(lines, start=1):
        if fence is not None:
            depth, body = _quote_split(raw, fence_quote)
            if depth == fence_quote:
                char, length, fence_base = fence
                blank = not body.strip(" \t")
                if not blank and _indent(body) < fence_base:
                    fence = None  # the list item that holds this fence has ended
                else:
                    kinds.append(FENCE)
                    prev_kind = FENCE
                    match = _FENCE_RE.match(body)
                    if (not blank and match and match.group("run")[0] == char
                            and len(match.group("run")) >= length and not match.group("info").strip(" \t")
                            and _indent(body) - fence_base <= 3):
                        fence = None
                    continue
            else:
                fence = None  # the blockquote that holds this fence has ended

        depth, text = _quote_split(raw)
        if depth != prev_depth:
            list_base = None
            code_base = None
            paragraph_open = False
        prev_depth = depth

        blank = not text.strip(" \t")
        indent = _indent(text)

        if blank:
            kinds.append(BLANK)
            prev_kind = BLANK
            paragraph_open = False
            continue

        if code_base is not None:
            if indent - code_base >= 4:
                kinds.append(CODE)
                prev_kind = CODE
                continue
            code_base = None

        item = _list_item_content(text)
        heading = bool(_HEADING_RE.match(text))
        is_break = bool(_THEMATIC_BREAK_RE.match(text))
        fence_match = _FENCE_RE.match(text)
        if list_base is not None and indent < list_base and (item is None or is_break):
            lazy = prev_kind == TEXT and paragraph_open and not (heading or is_break or fence_match)
            if not lazy:
                list_base = None

        base = list_base if list_base is not None else 0
        relative = indent - base

        if relative >= 4 and not paragraph_open:
            code_base = base
            kinds.append(CODE)
            prev_kind = CODE
            continue

        # A fence may open on a list-item line; its body is then the item's content.
        item_fence = None
        if item is not None and not is_break and relative <= 3:
            candidate = _FENCE_RE.match(_LIST_ITEM_RE.match(text).group("rest"))
            if candidate is not None and _fence_info_ok(candidate):
                item_fence = candidate
                list_base = item
        opener, fence_base = (item_fence, item) if item_fence is not None else (fence_match, base)
        if opener is not None and (item_fence is not None
                                   or (relative <= 3 and _fence_info_ok(opener))):
            fence = (opener.group("run")[0], len(opener.group("run")), fence_base)
            fence_quote = depth
            fence_line = number
            kinds.append(FENCE)
            prev_kind = FENCE
            paragraph_open = False
            continue

        kinds.append(TEXT)
        prev_kind = TEXT
        if heading or is_break:
            paragraph_open = False
        elif item is not None and relative <= 3:
            list_base = item
            paragraph_open = True
        else:
            paragraph_open = True

    return kinds, (fence_line if fence is not None else None)


def _would_extract(raw: str) -> bool:
    """True when a line would have produced a finding if it had been read as text."""
    return bool(_META_RE.match(raw) or _APPROVAL_RE.match(raw) or _BLOCKER_RE.match(raw)
                or _TEST_CLAIM_RE.search(raw) or _LINK_RE.search(raw))


def _split_lines(text: str) -> list[str]:
    lines = _LINE_END_RE.split(text)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _box_checked(match: re.Match) -> bool:
    """True for a task checkbox that is ticked, ``[x]`` or ``[X]``."""
    return match.group("box") in ("x", "X")


def parse_handoff(text: str, path_label: str) -> HandoffDocument:
    doc = HandoffDocument(path_label=path_label)
    in_evidence = False
    seen_refs: set[tuple[str, str]] = set()
    lines = _split_lines(text)
    kinds, unclosed_line = _scan_blocks(lines)

    for lineno, raw in enumerate(lines, start=1):
        if kinds[lineno - 1] != TEXT:
            continue

        heading = _HEADING_RE.match(raw)
        if heading:
            in_evidence = heading.group("title").strip().lower() in {"evidence", "evidence references"}
            continue

        meta = _META_RE.match(raw)
        if meta:
            key = meta.group("key").lower()
            value = meta.group("value").strip("`'\"")
            doc.metadata_lines.append(lineno)
            if key == "branch":
                if doc.branch is None:
                    doc.branch = value
                    doc.branch_line = lineno
                elif doc.branch != value:
                    doc.warnings.append(f"line {lineno}: conflicting branch value {value!r}")
            else:
                if not _SHA_RE.match(value):
                    doc.warnings.append(f"line {lineno}: {key} value is not a hex revision: {value!r}")
                elif doc.head is None:
                    doc.head = value.lower()
                    doc.head_line = lineno
                elif doc.head != value.lower():
                    doc.warnings.append(f"line {lineno}: conflicting revision value {value!r}")

        approval = _APPROVAL_RE.match(raw)
        if approval:
            if _box_checked(approval):
                doc.checked_items.append(CheckedItem(line=lineno, kind="approval",
                                                     text=approval.group("text")))
            else:
                doc.pending_approvals.append(PendingApproval(line=lineno, text=approval.group("text")))

        blocker = _BLOCKER_RE.match(raw)
        if blocker:
            if _box_checked(blocker):
                doc.checked_items.append(CheckedItem(line=lineno, kind="blocker",
                                                     text=blocker.group("text")))
            else:
                doc.blockers.append(Blocker(line=lineno, text=blocker.group("text")))

        if _TEST_CLAIM_RE.search(raw):
            doc.test_claims.append(TestClaim(line=lineno, text=raw.strip()[:200]))

        for m in _LINK_RE.finditer(raw):
            target = m.group("target")
            if is_url(target):
                continue
            target = target.split("#", 1)[0]
            if target and ("link", target) not in seen_refs:
                seen_refs.add(("link", target))
                doc.references.append(Reference(kind="link", target=target, line=lineno))

        if in_evidence:
            for m in _CODE_PATH_RE.finditer(raw):
                target = m.group("path")
                if is_url(target) or "/" not in target and "." not in target:
                    continue
                if ("evidence_path", target) not in seen_refs:
                    seen_refs.add(("evidence_path", target))
                    doc.references.append(Reference(kind="evidence_path", target=target, line=lineno))

        if len(doc.references) > MAX_REFERENCES:
            doc.warnings.append(f"reference list truncated at {MAX_REFERENCES} entries")
            doc.references = doc.references[:MAX_REFERENCES]
            break

    if unclosed_line is not None:
        hidden = [n for n in range(unclosed_line + 1, len(lines) + 1) if _would_extract(lines[n - 1])]
        if hidden:
            doc.warnings.append(
                f"line {unclosed_line}: code fence is never closed, so {len(hidden)} line(s) after it "
                f"(first at line {hidden[0]}) were not read as Markdown. Close the fence."
            )
    return doc
