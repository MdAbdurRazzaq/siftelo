"""TRC-011: task-list markers and fenced code inside blockquotes.

Written before the change and run against the TRC-010 parser to establish RED.

* An unchecked task item with an exact Blocked:, Blocker: or Pending approval: marker is an
  unresolved author-reported condition, in unordered and ordered lists.
* A checked task ([x] or [X]) is not an active blocker or pending approval, and it is not
  treated as proof of resolution. It is recorded so the report can surface it for review.
* A fence inside a blockquote holds its body as code. Markers in it are examples, not blockers.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src/ on sys.path)
from siftelo.handoff import parse_handoff


def _blockers(text: str) -> list[int]:
    return [b.line for b in parse_handoff(text, "h.md").blockers]


def _pending(text: str) -> list[int]:
    return [p.line for p in parse_handoff(text, "h.md").pending_approvals]


def _checked(text: str) -> list[tuple[int, str]]:
    return [(c.line, c.kind) for c in parse_handoff(text, "h.md").checked_items]


class UncheckedTasksAreUnresolved(unittest.TestCase):
    def test_unordered_unchecked_blocked(self) -> None:
        self.assertEqual(_blockers("- [ ] Blocked: waiting for API\n"), [1])

    def test_unordered_asterisk_unchecked_blocker(self) -> None:
        self.assertEqual(_blockers("* [ ] Blocker: waiting for review\n"), [1])

    def test_unordered_plus_unchecked(self) -> None:
        self.assertEqual(_blockers("+ [ ] Blocked: waiting for review\n"), [1])

    def test_ordered_dot_unchecked(self) -> None:
        self.assertEqual(_blockers("1. [ ] Blocked: waiting for API\n"), [1])

    def test_ordered_paren_unchecked(self) -> None:
        self.assertEqual(_blockers("2) [ ] Blocker: waiting for API\n"), [1])

    def test_nested_unchecked(self) -> None:
        self.assertEqual(_blockers("- parent\n  - [ ] Blocked: nested\n"), [2])

    def test_reason_text_is_kept_as_written(self) -> None:
        doc = parse_handoff("- [ ] Blocked: waiting for API   \n", "h.md")
        self.assertEqual([b.text for b in doc.blockers], ["waiting for API"])

    def test_unchecked_pending_approval_is_pending(self) -> None:
        self.assertEqual(_pending("- [ ] Pending approval: publish\n"), [1])

    def test_ordered_unchecked_pending_approval_is_pending(self) -> None:
        self.assertEqual(_pending("1. [ ] Pending approval: publish\n"), [1])


class CheckedTasksAreNotActive(unittest.TestCase):
    def test_lowercase_x_is_not_an_active_blocker(self) -> None:
        text = "- [x] Blocked: done\n"
        self.assertEqual(_blockers(text), [])
        self.assertEqual(_checked(text), [(1, "blocker")])

    def test_uppercase_x_is_not_an_active_blocker(self) -> None:
        text = "- [X] Blocker: done\n"
        self.assertEqual(_blockers(text), [])
        self.assertEqual(_checked(text), [(1, "blocker")])

    def test_ordered_checked_is_not_an_active_blocker(self) -> None:
        text = "1. [x] Blocked: done\n"
        self.assertEqual(_blockers(text), [])
        self.assertEqual(_checked(text), [(1, "blocker")])

    def test_checked_pending_approval_is_not_pending(self) -> None:
        text = "- [x] Pending approval: publish\n"
        self.assertEqual(_pending(text), [])
        self.assertEqual(_checked(text), [(1, "approval")])

    def test_checked_item_is_not_recorded_as_resolved_or_verified(self) -> None:
        doc = parse_handoff("- [x] Blocked: done\n", "h.md")
        self.assertEqual(doc.blockers, [])
        self.assertEqual([c.kind for c in doc.checked_items], ["blocker"])
        self.assertFalse(hasattr(doc.checked_items[0], "verified"))


class GenuineMarkersStillCount(unittest.TestCase):
    def test_plain_bullet_blocked(self) -> None:
        self.assertEqual(_blockers("- Blocked: x\n"), [1])

    def test_plain_blocker_without_list(self) -> None:
        self.assertEqual(_blockers("Blocker: x\n"), [1])

    def test_plain_ordered_blocked(self) -> None:
        self.assertEqual(_blockers("1. Blocked: x\n"), [1])

    def test_plain_blockquote_blocked(self) -> None:
        self.assertEqual(_blockers("> Blocked: x\n"), [1])

    def test_prose_is_not_a_marker(self) -> None:
        self.assertEqual(_blockers("The release was blocked by CI.\n"), [])

    def test_empty_task_reason_is_not_a_blocker(self) -> None:
        self.assertEqual(_blockers("- [ ] Blocked:\n"), [])


class TaskMarkersNeedAListMarker(unittest.TestCase):
    def test_checkbox_without_a_list_marker_is_not_a_task(self) -> None:
        self.assertEqual(_blockers("[ ] Blocked: x\n"), [])

    def test_task_without_a_marker_is_ignored(self) -> None:
        text = "- [ ] Write the docs\n- [x] Write the tests\n"
        doc = parse_handoff(text, "h.md")
        self.assertEqual((doc.blockers, doc.pending_approvals, doc.checked_items), ([], [], []))


class BlockquoteTasks(unittest.TestCase):
    def test_unchecked_task_in_blockquote_is_read(self) -> None:
        self.assertEqual(_blockers("> - [ ] Blocked: x\n"), [1])

    def test_checked_task_in_blockquote_is_not_active(self) -> None:
        text = "> - [x] Blocked: x\n"
        self.assertEqual(_blockers(text), [])
        self.assertEqual(_checked(text), [(1, "blocker")])


class TaskExamplesAreNotRead(unittest.TestCase):
    def test_task_in_a_fence_is_ignored(self) -> None:
        self.assertEqual(_blockers("```\n- [ ] Blocked: example\n```\n"), [])

    def test_checked_task_in_a_fence_is_ignored(self) -> None:
        self.assertEqual(_checked("```\n- [x] Blocked: example\n```\n"), [])

    def test_task_in_indented_code_is_ignored(self) -> None:
        self.assertEqual(_blockers("    - [ ] Blocked: example\n"), [])


class BlockquoteFences(unittest.TestCase):
    """The confirmed false blocker: a fence inside a blockquote was read as text."""

    def test_fence_inside_blockquote_hides_marker(self) -> None:
        doc = parse_handoff("> ```\n> Blocked: example\n> ```\n", "h.md")
        self.assertEqual(doc.blockers, [])
        self.assertEqual(doc.warnings, [])

    def test_fence_inside_blockquote_hides_task_marker(self) -> None:
        self.assertEqual(_blockers("> ```\n> - [ ] Blocked: example\n> ```\n"), [])

    def test_blocker_after_a_quoted_fence_is_read(self) -> None:
        self.assertEqual(_blockers("> ```\n> x\n> ```\n> Blocked: real\n"), [4])

    def test_leaving_the_quote_ends_an_open_quoted_fence(self) -> None:
        doc = parse_handoff("> ```\n> code\nBlocked: real\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [3])
        self.assertEqual(doc.warnings, [])

    def test_fence_inside_a_quoted_list_item_hides_marker(self) -> None:
        self.assertEqual(_blockers("> - item\n>   ```\n>   Blocked: example\n>   ```\n"), [])

    def test_top_level_fence_keeps_quote_marker_text_as_code(self) -> None:
        self.assertEqual(_blockers("```\n> Blocked: example\n```\n"), [])

    def test_indented_code_inside_blockquote_is_code(self) -> None:
        self.assertEqual(_blockers(">     Blocked: example\n"), [])


class PreflightSurfacesTasks(unittest.TestCase):
    """End to end through run_preflight: unchecked items are unresolved, checked ones are surfaced."""

    def _run(self, text: str):
        from siftelo.preflight import run_preflight
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "handoff.md").write_text(text, encoding="utf-8")
            return run_preflight(tmp, "handoff.md")

    def test_unchecked_blocker_is_an_unresolved_blocker(self) -> None:
        report = self._run("- [ ] Blocked: waiting for API\n")
        blockers = [f for f in report.findings if f.category == "blocker"]
        self.assertEqual(len(blockers), 1)
        self.assertEqual(report.readiness()["outcome"], "review_required")

    def test_checked_task_is_surfaced_for_review_not_as_a_blocker(self) -> None:
        report = self._run("- [x] Blocked: done\n")
        self.assertEqual([f for f in report.findings if f.category == "blocker"], [])
        surfaced = [f for f in report.findings if f.category == "task_done"]
        self.assertEqual(len(surfaced), 1)
        self.assertEqual(surfaced[0].status, "agent_reported")
        self.assertIn("not verified as resolved", surfaced[0].message)
        self.assertEqual(report.readiness()["outcome"], "review_required")
        self.assertTrue(any("checked" in r for r in report.readiness()["reasons"]))

    def test_checked_pending_approval_is_surfaced_not_pending(self) -> None:
        report = self._run("- [X] Pending approval: publish\n")
        self.assertEqual([f for f in report.findings if f.category == "approval"], [])
        self.assertEqual(len([f for f in report.findings if f.category == "task_done"]), 1)


if __name__ == "__main__":
    unittest.main()
