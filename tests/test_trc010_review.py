"""TRC-010 review regressions: findings from the independent security review of TRC-010.

Written before each fix and run against the TRC-010 implementation to establish RED.
Each class is named after the finding it covers (F1 to F11 in the TRC-010 report).
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts src/ on sys.path)
from siftelo import gitinspect, report
from siftelo.handoff import parse_handoff
from siftelo.preflight import Finding, PreflightReport


def _synthetic(findings: list[Finding]) -> PreflightReport:
    repository = {"is_repo": True, "root": "/r", "head": "a" * 40, "branch": "main",
                  "status_inspected": True, "dirty": False, "notes": []}
    return PreflightReport(project_root="/r", handoff="h.md", manifest=None,
                           repository=repository, findings=findings)


# F1: a fence opener that starts with a non-ASCII space is paragraph text to a Markdown renderer.
class F1NonAsciiSpaceBeforeFence(unittest.TestCase):
    def test_nbsp_before_backticks_is_not_a_fence(self) -> None:
        doc = parse_handoff(" ```\nBlocked: real reason.\nPending approval: deploy.\n ```\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [2])
        self.assertEqual([p.line for p in doc.pending_approvals], [3])


# F2: Markdown ends a line only at LF, CR or CRLF. Unicode separators are ordinary characters.
class F2LineSplitting(unittest.TestCase):
    def test_unicode_line_separator_does_not_start_a_new_line(self) -> None:
        doc = parse_handoff("x ```\nBlocked: real reason.\ny ```\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [2])

    def test_form_feed_does_not_split_a_fence(self) -> None:
        doc = parse_handoff("x\x0c```\nBlocked: real reason.\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [2])


# F3: a thematic break ends a list, so an indented fence after it is code, not a fence.
class F3ThematicBreakEndsList(unittest.TestCase):
    def test_indented_fence_after_thematic_break_is_code(self) -> None:
        doc = parse_handoff("- a\n---\n    ```\nBlocked: real reason.\n    ```\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [4])


# F4: a fence inside a list item closes at a closer indented relative to the item's content column.
class F4ListFenceCloserIsRelative(unittest.TestCase):
    def test_closer_indented_four_inside_list_item_closes_the_fence(self) -> None:
        doc = parse_handoff("- item\n  ```\n  code\n    ```\nBlocked: real reason.\n  ```\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [5])


# A list fence ends with its list: a blank line and then unindented text ends the item.
class ListFenceEndsWithItem(unittest.TestCase):
    def test_unindented_text_after_a_blank_line_closes_a_list_fence(self) -> None:
        doc = parse_handoff("- item\n  ```\n  body\n\nBlocked: real reason.\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [5])
        self.assertEqual(doc.warnings, [])


# F5: list and quote markers a renderer shows as a list item or a blockquote must still be read.
class F5MarkerForms(unittest.TestCase):
    def test_plus_bullet_marker_is_read(self) -> None:
        self.assertEqual([b.line for b in parse_handoff("+ Blocked: real reason.\n", "h.md").blockers], [1])

    def test_ordered_marker_is_read(self) -> None:
        self.assertEqual([b.line for b in parse_handoff("1. Blocked: real reason.\n", "h.md").blockers], [1])

    def test_blockquote_marker_is_read(self) -> None:
        self.assertEqual([b.line for b in parse_handoff("> Blocked: real reason.\n", "h.md").blockers], [1])

    def test_ordered_pending_approval_is_read(self) -> None:
        doc = parse_handoff("1. Pending approval: publish.\n", "h.md")
        self.assertEqual([p.line for p in doc.pending_approvals], [1])

    def test_ordered_branch_is_read(self) -> None:
        self.assertEqual(parse_handoff("1. Branch: main\n", "h.md").branch, "main")


# F6, F7, F8: invisible and bidi format characters, lone surrogates, and spoofable escapes.
class F6F7F8Escapes(unittest.TestCase):
    def test_format_characters_are_escaped(self) -> None:
        for ch in ("؜", "​", "⁠", "﻿", "\U000e0041"):
            with self.subTest(ch=hex(ord(ch))):
                self.assertNotIn(ch, report.safe_text(ch))

    def test_lone_surrogate_is_escaped_and_output_encodes(self) -> None:
        self.assertEqual(report.safe_text("\udc80"), "\\udc80")
        report.to_markdown(_synthetic([Finding("agent_reported", "claim", "c", "bad \udc80", "manifest")])).encode("utf-8")

    def test_escape_cannot_be_spoofed_by_literal_text(self) -> None:
        self.assertNotEqual(report.safe_text("\x1b"), report.safe_text("\\x1b"))
        self.assertNotEqual(report.safe_text("`"), report.safe_text("\\x60"))

    def test_backslash_before_an_escape_pattern_is_escaped(self) -> None:
        self.assertEqual(report.safe_text("\\x41"), "\\x5cx41")

    # Added after the review fixes, as a guard on the narrower backslash rule: ordinary
    # Windows paths must stay readable.
    def test_windows_path_with_backslashes_stays_readable(self) -> None:
        self.assertEqual(report.safe_text("C:\\Users\\synthetic-user"), "C:\\Users\\synthetic-user")
        self.assertEqual(report.safe_text("\\xyz"), "\\xyz")


# F9: links, images and HTML in untrusted prose must not render as Markdown.
class F9InlineMarkdown(unittest.TestCase):
    def test_link_and_image_brackets_are_escaped_in_prose(self) -> None:
        out = report.safe_text("[x](http://evil) ![p](http://evil/p.png)")
        self.assertNotIn("[", out)
        self.assertNotIn("]", out)

    def test_html_angle_brackets_are_escaped_in_prose(self) -> None:
        out = report.safe_text("<img src=x>")
        self.assertNotIn("<", out)

    def test_code_span_context_keeps_brackets_readable(self) -> None:
        self.assertEqual(report.safe_text("a[b]", code=True), "a[b]")


# F11: a failure while reading output must not look like a successful, partial result.
class F11ReaderFailure(unittest.TestCase):
    def test_reader_error_is_an_error_not_partial_output(self) -> None:
        class BrokenStream:
            def __init__(self) -> None:
                self._sent = False

            def read1(self, n: int) -> bytes:
                if not self._sent:
                    self._sent = True
                    return b"PARTIAL"
                raise OSError("simulated read failure")

            def close(self) -> None:
                pass

        class FakeProcess:
            pid = 2 ** 22  # no such process: kill attempts fail harmlessly
            returncode = 0

            def __init__(self, *args, **kwargs) -> None:
                self.stdout = BrokenStream()

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def kill(self) -> None:
                pass

        with mock.patch.object(gitinspect.subprocess, "Popen", FakeProcess):
            with self.assertRaises(gitinspect.GitError):
                gitinspect.run_bounded(["git", "status"], cwd=gitinspect.Path.cwd(),
                                       env=gitinspect.safe_environment(), timeout=5, max_bytes=4096)


# F10: an interrupt while waiting for output must not leave the child running.
class F10InterruptCleanup(unittest.TestCase):
    def test_keyboard_interrupt_kills_and_reaps_the_child(self) -> None:
        started: list[subprocess.Popen] = []
        real_popen = subprocess.Popen

        def spy(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            started.append(proc)
            return proc

        real_join = gitinspect.threading.Thread.join
        calls = {"n": 0}

        def join_once_interrupted(self, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise KeyboardInterrupt
            return real_join(self, timeout)

        with mock.patch.object(gitinspect.subprocess, "Popen", side_effect=spy), \
                mock.patch.object(gitinspect.threading.Thread, "join", join_once_interrupted):
            with self.assertRaises(KeyboardInterrupt):
                gitinspect.run_bounded([sys.executable, "-c", "import time; time.sleep(30)"],
                                       cwd=gitinspect.Path.cwd(), env=gitinspect.safe_environment(),
                                       timeout=20, max_bytes=4096)
        self.assertTrue(started)
        self.assertIsNotNone(started[0].poll(), "child still running after interrupt")


# Re-review findings (second independent review of the TRC-010 fixes).


# R1: a fence opened on a list-item line is a fence, so its body is never read as a blocker.
class R1ListItemFence(unittest.TestCase):
    def test_fence_opened_on_bullet_line_hides_its_body(self) -> None:
        doc = parse_handoff("- ```bash\n  Blocked: fake\n  ```\n", "h.md")
        self.assertEqual(doc.blockers, [])

    def test_fence_opened_on_ordered_line_hides_its_body(self) -> None:
        doc = parse_handoff("1. ```\n   Blocked: fake\n   ```\n", "h.md")
        self.assertEqual(doc.blockers, [])

    def test_blocker_after_a_closed_list_item_fence_is_read(self) -> None:
        doc = parse_handoff("- ```\n  code\n  ```\n  Blocked: real\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [4])
        self.assertEqual(doc.warnings, [])


# R2: a spaced thematic break (`* * *`, `- - -`) ends a list, as `---` already does.
class R2SpacedThematicBreakEndsList(unittest.TestCase):
    def test_spaced_asterisks_end_the_list(self) -> None:
        doc = parse_handoff("- a\n\n* * *\n\n    Blocked: code\n", "h.md")
        self.assertEqual(doc.blockers, [])

    def test_spaced_dashes_end_the_list(self) -> None:
        doc = parse_handoff("- a\n- - -\n    Blocked: code\n", "h.md")
        self.assertEqual(doc.blockers, [])


# R3: only spaces and tabs may follow a closing fence. Other Unicode spaces keep the fence open.
class R3ClosingFenceWhitespace(unittest.TestCase):
    def test_no_break_space_after_closer_does_not_close_the_fence(self) -> None:
        doc = parse_handoff("```\nx\n``` \nBlocked: code\n```\n", "h.md")
        self.assertEqual(doc.blockers, [])
        self.assertEqual(doc.warnings, [])


# R4: any failure to start Git is a GitError, not a raw traceback.
class R4GitStartErrors(unittest.TestCase):
    def test_permission_error_on_start_is_a_git_error(self) -> None:
        with mock.patch.object(gitinspect.subprocess, "Popen", side_effect=PermissionError("denied")):
            with self.assertRaises(gitinspect.GitError):
                gitinspect.run_bounded(["git", "status"], cwd=gitinspect.Path.cwd(),
                                       env=gitinspect.safe_environment(), timeout=5, max_bytes=4096)


if __name__ == "__main__":
    unittest.main()
