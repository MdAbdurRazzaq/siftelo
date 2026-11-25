"""TRC-009 regressions: Blocked:/Blocker: markers inside fenced Markdown code blocks.

Written before the fix and run against the TRC-007 implementation to establish RED.
Every test uses a temporary synthetic repository; nothing outside it is touched.

A marker that appears inside a fenced code block is an example, not an open blocker.
A marker after an unclosed fence is never silently dropped: it produces a warning, so the
outcome cannot become "no contradiction detected" by accident.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from helpers import exclude_from_status, head_of, make_repo, temp_dir, write

from siftelo import preflight
from siftelo.handoff import parse_handoff


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.repo = make_repo(self.tmp, {"docs/notes.md": "notes\n"}, branch="feature/x")
        self.head = head_of(self.repo)

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def _handoff(self, text: str) -> str:
        write(self.repo, "handoff.md", text)
        exclude_from_status(self.repo, "handoff.md")
        return "handoff.md"

    def _run(self, handoff: str) -> preflight.PreflightReport:
        return preflight.run_preflight(self.repo, handoff)

    def _clean(self, extra: str) -> str:
        return f"# Handoff\n\nBranch: feature/x\nHEAD: {self.head}\n\n{extra}"

    def _blockers(self, report) -> list:
        return [f for f in report.findings if f.category == "blocker"]

    def _unknown_warnings(self, report) -> list:
        return [f for f in report.findings if f.status == "unknown" and f.category == "handoff"]


# --------------------------------------------------------------------------
# Part 1: markers inside closed fenced blocks are examples, not blockers
# --------------------------------------------------------------------------
class FencedExamplesAreNotBlockers(_Base):
    def _assert_example_only(self, extra: str) -> None:
        report = self._run(self._handoff(self._clean(extra)))
        self.assertEqual(self._blockers(report), [], extra)
        self.assertEqual(report.exit_code(), 0, extra)

    def test_backtick_fence_example_is_not_a_blocker(self) -> None:
        self._assert_example_only("```markdown\nBlocked: example reason.\n```\n")

    def test_tilde_fence_example_is_not_a_blocker(self) -> None:
        self._assert_example_only("~~~\nBlocker: example reason.\n~~~\n")

    def test_fence_with_info_string_example_is_not_a_blocker(self) -> None:
        self._assert_example_only("```text\n- Blocked: example reason.\n```\n")

    def test_longer_fence_is_closed_only_by_a_fence_at_least_as_long(self) -> None:
        # The three-backtick line does not close a four-backtick fence.
        self._assert_example_only("````markdown\n```\nBlocked: still an example.\n````\n")

    def test_fence_is_closed_only_by_the_same_character(self) -> None:
        # A tilde line does not close a backtick fence.
        self._assert_example_only("```\n~~~\nBlocked: still an example.\n```\n")

    def test_parser_level_fenced_marker_is_not_recorded(self) -> None:
        doc = parse_handoff("```\nBlocked: example.\n```\n", "h.md")
        self.assertEqual(doc.blockers, [])
        self.assertEqual(doc.warnings, [])


# --------------------------------------------------------------------------
# Part 2: real blockers outside fences are still recorded (guards)
# --------------------------------------------------------------------------
class RealBlockersOutsideFencesStillWork(_Base):
    def test_blocker_after_closed_fence_is_recorded_at_its_own_line(self) -> None:
        h = self._handoff(self._clean("```\nBlocked: example.\n```\n\nBlocked: real reason.\n"))
        report = self._run(h)
        self.assertEqual([b.evidence for b in self._blockers(report)], ["handoff:10"])
        self.assertEqual(report.exit_code(), 3)

    def test_blocker_before_a_fence_is_recorded(self) -> None:
        h = self._handoff(self._clean("Blocked: real reason.\n\n```\nBlocked: example.\n```\n"))
        report = self._run(h)
        self.assertEqual([b.evidence for b in self._blockers(report)], ["handoff:6"])
        self.assertEqual(report.exit_code(), 3)

    def test_blocker_after_a_tilde_fence_is_recorded(self) -> None:
        h = self._handoff(self._clean("~~~\nBlocker: example.\n~~~\nBlocker: real reason.\n"))
        report = self._run(h)
        self.assertEqual([b.evidence for b in self._blockers(report)], ["handoff:9"])

    def test_real_blocker_still_blocks_when_a_contradiction_is_also_present(self) -> None:
        h = self._handoff(f"# Handoff\n\nBranch: feature/x\nHEAD: {'0' * 40}\n\n"
                          "```\nBlocked: example.\n```\n\nBlocked: real reason.\n")
        report = self._run(h)
        self.assertEqual(report.exit_code(), 1)
        self.assertEqual(len(self._blockers(report)), 1)


# --------------------------------------------------------------------------
# Part 3: an unclosed fence hides nothing silently
# --------------------------------------------------------------------------
class UnclosedFenceIsReported(_Base):
    def test_marker_after_unclosed_fence_is_not_recorded_but_is_warned(self) -> None:
        report = self._run(self._handoff(self._clean("```\nBlocked: real reason.\n")))
        self.assertEqual(self._blockers(report), [])
        warnings = [f.message for f in self._unknown_warnings(report)]
        self.assertTrue(any("never closed" in w for w in warnings), warnings)
        self.assertEqual(report.exit_code(), 3)

    def test_unclosed_fence_without_markers_gives_no_warning(self) -> None:
        report = self._run(self._handoff(self._clean("```\nplain example text\n")))
        self.assertEqual(self._unknown_warnings(report), [])

    def test_parser_warns_on_unclosed_fence_with_marker(self) -> None:
        doc = parse_handoff("```\nBlocked: real reason.\n", "h.md")
        self.assertEqual(doc.blockers, [])
        self.assertTrue(any("never closed" in w for w in doc.warnings), doc.warnings)


if __name__ == "__main__":
    unittest.main()
