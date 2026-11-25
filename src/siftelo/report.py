"""Render a PreflightReport as deterministic JSON or Markdown.

Both formats carry the same `readiness` object. Its `no_contradiction_detected`
outcome is explicitly not verified readiness, and nothing in the report
authorises an action.
"""

from __future__ import annotations

import json
import string
import unicodedata

from .preflight import PreflightReport

SCHEMA = "siftelo/preflight-report"
SCHEMA_VERSION = 2

_DISCLAIMER = (
    "`no_contradiction_detected` means these checks found no contradiction. It is not verified "
    "readiness, and it authorises nothing. Pending or granted approvals, claims and evidence "
    "are reported for review only."
)

_NEXT_STEPS_BY_STATUS = {
    "stale": "Resolve every `stale` finding before relying on the handoff.",
    "rejected": "Fix or remove `rejected` references; they were deliberately not followed.",
    "unknown": "Review `unknown` items manually; this tool could not establish them.",
    "agent_reported": "Treat `agent_reported` items as the author's claims. Verify them independently.",
}

# Unicode general categories shown as escapes: control, format (includes bidirectional
# controls and zero-width characters), surrogate, private use, unassigned, and the line
# and paragraph separators.
_ESCAPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
# Characters that start Markdown links, images, emphasis or HTML. Escaped in prose only;
# inside a code span they are literal.
_PROSE_ONLY_ESCAPES = "[]<>"
# Hex digits that follow \x, \u or \U in an escape this module emits (2, 4 or 8 digits).
_HEX_DIGITS_AFTER = {"x": 2, "u": 4, "U": 8}


def _escape_char(ch: str, code: bool) -> str | None:
    """Return the visible escape for one character, or None when it is shown as it is."""
    if ch == "`":
        return "\\x60"
    if ch == "\n":
        return "\\n"
    if ch == "\r":
        return "\\r"
    if ch == "\t":
        return "\\t"
    if not code and ch in _PROSE_ONLY_ESCAPES:
        return f"\\x{ord(ch):02x}"
    cp = ord(ch)
    if cp < 0x20 or 0x7F <= cp <= 0x9F or unicodedata.category(ch) in _ESCAPED_CATEGORIES:
        if cp < 0x100:
            return f"\\x{cp:02x}"
        if cp < 0x10000:
            return f"\\u{cp:04x}"
        return f"\\U{cp:08x}"
    return None


def _would_read_as_escape(text: str, index: int, code: bool) -> bool:
    """True when the backslash at `index` would combine with the text after it into an escape.

    The check looks at the raw characters that follow. Hex digits are never escaped, so
    the same test applies to the output. Ordinary Windows paths such as ``C:\\Users`` stay
    readable, because ``\\U`` is not followed by eight hex digits.
    """
    following = text[index + 1] if index + 1 < len(text) else ""
    if not following:
        return False
    if following in "nrt":
        return True
    width = _HEX_DIGITS_AFTER.get(following)
    if width is not None:
        digits = text[index + 2:index + 2 + width]
        return len(digits) == width and all(ch in string.hexdigits for ch in digits)
    return _escape_char(following, code) is not None


def safe_text(value: object, *, code: bool = False) -> str:
    """Make untrusted text safe for one line of the Markdown report.

    Line breaks, control and format characters, lone surrogates, bidirectional
    overrides and line separators are shown as visible escapes (for example ``\\x1b``,
    ``\\u202e`` or ``\\U000e0041``), so they cannot start a new line, forge a finding,
    or change how a terminal displays the report. Backticks are escaped so they cannot
    end a code span. In prose (``code=False``), square brackets and angle brackets are
    escaped too, so untrusted text cannot start a Markdown link, image or HTML element.

    A backslash is escaped when it could otherwise combine with the next character
    into an escape this module emits, so literal text such as ``\\x41`` cannot pass as
    an escape. Escapes are visible text: a literal ``\\x1b`` in a handoff looks the
    same as an escaped ESC. The JSON renderer needs none of this, because
    `json.dumps` already escapes these characters.
    """
    text = str(value)
    out: list[str] = []
    for index, ch in enumerate(text):
        if ch == "\\":
            out.append("\\x5c" if _would_read_as_escape(text, index, code) else "\\")
            continue
        escaped = _escape_char(ch, code)
        out.append(ch if escaped is None else escaped)
    return "".join(out)


def to_dict(report: PreflightReport) -> dict:
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "project_root": report.project_root,
        "handoff": report.handoff,
        "manifest": report.manifest,
        "readiness": report.readiness(),
        "repository": report.repository,
        "summary": report.counts(),
        "errors": list(report.errors),
        "truncated": report.truncated,
        "findings": [f.as_dict() for f in report.findings],
        "exit_code": report.exit_code(),
    }


def to_json(report: PreflightReport) -> str:
    return json.dumps(to_dict(report), indent=2, sort_keys=True) + "\n"


def to_markdown(report: PreflightReport) -> str:
    lines: list[str] = []
    lines.append("# Siftelo Handoff Preflight")
    lines.append("")
    lines.append(f"- Project root: `{safe_text(report.project_root, code=True)}`")
    lines.append(f"- Handoff: `{safe_text(report.handoff, code=True)}`")
    lines.append(f"- Manifest: `{safe_text(report.manifest or 'none', code=True)}`")
    lines.append("")

    readiness = report.readiness()
    lines.append("## Readiness")
    lines.append("")
    lines.append(f"- Outcome: `{readiness['outcome']}`")
    lines.append(f"- Verified readiness: {'yes' if readiness['verified_readiness'] else 'no'}")
    lines.append(f"- Authorises actions: {'yes' if readiness['authorizes_actions'] else 'no'}")
    for reason in readiness["reasons"]:
        lines.append(f"- Reason: {safe_text(reason)}")
    lines.append("")
    lines.append(_DISCLAIMER)
    lines.append("")

    if report.errors:
        lines.append("## Errors")
        lines.append("")
        for err in report.errors:
            lines.append(f"- {safe_text(err)}")
        lines.append("")
        return "\n".join(lines) + "\n"

    repo = report.repository
    lines.append("## Repository")
    lines.append("")
    lines.append(f"- Git root: `{safe_text(repo.get('root') or 'n/a', code=True)}`")
    lines.append(f"- Branch: `{safe_text(repo.get('branch') or 'detached/unknown', code=True)}`")
    lines.append(f"- HEAD: `{safe_text(repo.get('head') or 'unknown', code=True)}`")
    lines.append(f"- Working tree status inspected: {'yes' if repo.get('status_inspected') else 'no'}")
    lines.append(f"- Working tree dirty: {'yes' if repo.get('dirty') else 'no'}")
    for note in repo.get("notes", []):
        lines.append(f"- Note: {safe_text(note)}")
    lines.append("")

    counts = report.counts()
    lines.append("## Summary")
    lines.append("")
    lines.append("| status | count |")
    lines.append("|---|---|")
    for status in ["stale", "rejected", "unknown", "agent_reported", "verified_metadata"]:
        lines.append(f"| {status} | {counts[status]} |")
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    if not report.findings:
        lines.append("No findings.")
    for f in report.findings:
        lines.append(f"- **[{f.status}]** ({f.category}) {safe_text(f.subject)}: {safe_text(f.message)}")
        lines.append(f"  - evidence: `{safe_text(f.evidence, code=True)}`")
        if f.suggestion:
            lines.append(f"  - next: {safe_text(f.suggestion)}")
    if report.truncated:
        lines.append("")
        lines.append("_Output truncated to the maximum number of findings._")
    lines.append("")

    lines.append("## Suggested next verification")
    lines.append("")
    present = [s for s in ["stale", "rejected", "unknown", "agent_reported"] if counts[s]]
    if not present:
        lines.append("All checked metadata matches. Nothing was executed or verified beyond metadata.")
    for status in present:
        lines.append(f"- {_NEXT_STEPS_BY_STATUS[status]}")
    lines.append("")
    return "\n".join(lines) + "\n"
