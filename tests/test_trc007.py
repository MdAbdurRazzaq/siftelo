"""TRC-007 regressions: cross-source branch checks and explicit blocker recognition.

Written before the fix and run against the TRC-005 implementation to establish RED.
Every test uses a temporary synthetic repository; nothing outside it is touched.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from helpers import exclude_from_status, git, head_of, make_repo, temp_dir, write

from siftelo import preflight
from siftelo.handoff import parse_handoff

MANIFEST_BRANCH_EVIDENCE = "manifest:repository.expected_branch"


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
        exclude_from_status(self.repo, "handoff.md", "manifest.json")
        return "handoff.md"

    def _manifest(self, data: dict) -> str:
        write(self.repo, "manifest.json", json.dumps(data))
        return "manifest.json"

    def _run(self, handoff: str, manifest: str | None = None) -> preflight.PreflightReport:
        return preflight.run_preflight(self.repo, handoff, manifest)

    def _branch(self, report) -> list:
        return [f for f in report.findings if f.category == "repository" and f.subject == "branch"]

    def _head(self, report) -> list:
        return [f for f in report.findings if f.category == "repository" and f.subject == "head"]

    def _blockers(self, report) -> list:
        return [f for f in report.findings if f.category == "blocker"]


# --------------------------------------------------------------------------
# Part 1: both explicit branch sources are checked independently
# --------------------------------------------------------------------------
class BranchCrossCheck(_Base):
    def _handoff_with_branch(self, branch: str) -> str:
        return self._handoff(f"# Handoff\n\nBranch: {branch}\nHEAD: {self.head}\n")

    def test_manifest_matches_handoff_conflicts(self) -> None:
        h = self._handoff_with_branch("main")
        m = self._manifest({"schema_version": 1, "repository": {"expected_branch": "feature/x"}})
        report = self._run(h, m)
        by_evidence = {f.evidence: f for f in self._branch(report)}
        self.assertEqual(sorted(by_evidence), ["handoff:3", MANIFEST_BRANCH_EVIDENCE])
        self.assertEqual(by_evidence[MANIFEST_BRANCH_EVIDENCE].status, "verified_metadata")
        self.assertEqual(by_evidence["handoff:3"].status, "stale")
        self.assertEqual(report.exit_code(), 1)

    def test_handoff_matches_manifest_conflicts(self) -> None:
        h = self._handoff_with_branch("feature/x")
        m = self._manifest({"schema_version": 1, "repository": {"expected_branch": "main"}})
        report = self._run(h, m)
        by_evidence = {f.evidence: f for f in self._branch(report)}
        self.assertEqual(sorted(by_evidence), ["handoff:3", MANIFEST_BRANCH_EVIDENCE])
        self.assertEqual(by_evidence[MANIFEST_BRANCH_EVIDENCE].status, "stale")
        self.assertEqual(by_evidence["handoff:3"].status, "verified_metadata")
        self.assertEqual(report.exit_code(), 1)

    def test_both_sources_conflict(self) -> None:
        h = self._handoff_with_branch("main")
        m = self._manifest({"schema_version": 1, "repository": {"expected_branch": "develop"}})
        report = self._run(h, m)
        statuses = sorted(f.status for f in self._branch(report))
        self.assertEqual(statuses, ["stale", "stale"])
        self.assertEqual(report.exit_code(), 1)

    def test_both_sources_match(self) -> None:
        h = self._handoff_with_branch("feature/x")
        m = self._manifest({"schema_version": 1, "repository": {"expected_branch": "feature/x"}})
        report = self._run(h, m)
        statuses = sorted(f.status for f in self._branch(report))
        self.assertEqual(statuses, ["verified_metadata", "verified_metadata"])
        self.assertEqual(report.exit_code(), 0)

    def test_only_manifest_source(self) -> None:
        h = self._handoff(f"# Handoff\n\nHEAD: {self.head}\n")
        m = self._manifest({"schema_version": 1, "repository": {"expected_branch": "feature/x"}})
        report = self._run(h, m)
        branch = self._branch(report)
        self.assertEqual([(f.evidence, f.status) for f in branch],
                         [(MANIFEST_BRANCH_EVIDENCE, "verified_metadata")])

    def test_only_handoff_source(self) -> None:
        h = self._handoff_with_branch("main")
        report = self._run(h)
        branch = self._branch(report)
        self.assertEqual([(f.evidence, f.status) for f in branch], [("handoff:3", "stale")])

    def test_handoff_branch_evidence_points_at_the_branch_line(self) -> None:
        # The HEAD line comes first. The branch evidence must name the Branch line (line 4), not line 3.
        h = self._handoff(f"# Handoff\n\nHEAD: {self.head}\nBranch: main\n")
        report = self._run(h)
        self.assertEqual([f.evidence for f in self._branch(report)], ["handoff:4"])

    def test_handoff_head_evidence_points_at_the_head_line(self) -> None:
        # The Branch line comes first. The HEAD evidence must name the HEAD line (line 4), not line 3.
        h = self._handoff(f"# Handoff\n\nBranch: feature/x\nHEAD: {self.head}\n")
        report = self._run(h)
        self.assertEqual([f.evidence for f in self._head(report)], ["handoff:4"])

    def test_conflicting_handoff_branch_is_never_verified(self) -> None:
        h = self._handoff_with_branch("main")
        m = self._manifest({"schema_version": 1, "repository": {"expected_branch": "feature/x"}})
        report = self._run(h, m)
        verified_from_handoff = [f for f in self._branch(report)
                                 if f.evidence.startswith("handoff:") and f.status == "verified_metadata"]
        self.assertEqual(verified_from_handoff, [])

    def test_detached_head_marks_every_source_unknown(self) -> None:
        git(self.repo, "checkout", "-q", "--detach")
        h = self._handoff_with_branch("feature/x")
        m = self._manifest({"schema_version": 1, "repository": {"expected_branch": "feature/x"}})
        report = self._run(h, m)
        statuses = sorted(f.status for f in self._branch(report))
        self.assertEqual(statuses, ["unknown", "unknown"])
        self.assertEqual(report.exit_code(), 3)

    def test_no_branch_source_is_unknown(self) -> None:
        h = self._handoff(f"# Handoff\n\nHEAD: {self.head}\n")
        report = self._run(h)
        self.assertEqual([f.status for f in self._branch(report)], ["unknown"])


# --------------------------------------------------------------------------
# Part 2: narrow, explicit blocker markers
# --------------------------------------------------------------------------
class BlockerRecognition(_Base):
    def _clean(self, extra: str) -> str:
        return f"# Handoff\n\nBranch: feature/x\nHEAD: {self.head}\n\n{extra}"

    def test_blocked_marker_recorded_with_line_and_text(self) -> None:
        h = self._handoff(self._clean("Blocked: waiting for a maintainer reply.\n"))
        report = self._run(h)
        blockers = self._blockers(report)
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0].evidence, "handoff:6")
        self.assertIn("waiting for a maintainer reply.", blockers[0].message)
        self.assertEqual(report.exit_code(), 3)

    def test_blocker_marker_recorded(self) -> None:
        h = self._handoff(self._clean("Blocker: needs the API key from the owner.\n"))
        blockers = self._blockers(self._run(h))
        self.assertEqual([b.evidence for b in blockers], ["handoff:6"])

    def test_list_item_marker_recorded(self) -> None:
        h = self._handoff(self._clean("- Blocked: CI credentials not yet issued.\n"))
        blockers = self._blockers(self._run(h))
        self.assertEqual([b.evidence for b in blockers], ["handoff:6"])

    def test_blocker_is_reported_as_unverified_not_verified(self) -> None:
        h = self._handoff(self._clean("Blocked: waiting for review.\n"))
        blockers = self._blockers(self._run(h))
        self.assertEqual([b.status for b in blockers], ["agent_reported"])
        self.assertIn("not verified", blockers[0].message)

    def test_blocker_gives_review_required_with_its_own_reason(self) -> None:
        h = self._handoff(self._clean("Blocked: waiting for review.\n"))
        report = self._run(h)
        self.assertEqual(report.exit_code(), 3)
        reasons = report.readiness()["reasons"]
        self.assertTrue(any("unresolved blocker" in r for r in reasons), reasons)
        self.assertFalse(any("unverified claim" in r for r in reasons), reasons)

    def test_blocker_does_not_mask_a_contradiction(self) -> None:
        h = self._handoff(f"# Handoff\n\nBranch: feature/x\nHEAD: {'0' * 40}\n\nBlocked: waiting for review.\n")
        report = self._run(h)
        self.assertEqual(report.exit_code(), 1)
        self.assertEqual(len(self._blockers(report)), 1)

    def test_multiple_blockers_each_recorded(self) -> None:
        h = self._handoff(self._clean("Blocked: first reason.\n\nBlocker: second reason.\n"))
        blockers = self._blockers(self._run(h))
        self.assertEqual([b.evidence for b in blockers], ["handoff:6", "handoff:8"])


class BlockerNegatives(_Base):
    def _clean(self, extra: str) -> str:
        return f"# Handoff\n\nBranch: feature/x\nHEAD: {self.head}\n\n{extra}"

    def _assert_no_blocker_and_clean(self, extra: str) -> None:
        report = self._run(self._handoff(self._clean(extra)))
        self.assertEqual(self._blockers(report), [], extra)
        self.assertEqual(report.exit_code(), 0, extra)

    def test_ordinary_prose_containing_blocked_is_ignored(self) -> None:
        self._assert_no_blocker_and_clean("The release was blocked by a CI outage last week.\n")

    def test_blocked_mid_line_with_colon_is_ignored(self) -> None:
        self._assert_no_blocker_and_clean("Earlier this step was blocked: the CI outage.\n")

    def test_lowercase_marker_is_ignored(self) -> None:
        self._assert_no_blocker_and_clean("blocked: waiting for review.\n")

    def test_heading_with_marker_is_ignored(self) -> None:
        self._assert_no_blocker_and_clean("## Blocked: waiting for review\n")

    def test_marker_with_empty_reason_is_ignored(self) -> None:
        self._assert_no_blocker_and_clean("Blocked:\n")

    def test_unblocked_is_not_a_marker(self) -> None:
        self._assert_no_blocker_and_clean("Unblocked: the CI is working again.\n")

    def test_blocked_by_phrase_is_ignored(self) -> None:
        self._assert_no_blocker_and_clean("Blocked by the reviewer, see the notes.\n")


# --------------------------------------------------------------------------
# Parser level: the handoff document records blockers and branch/HEAD lines
# --------------------------------------------------------------------------
class ParserRecords(unittest.TestCase):
    def test_parser_records_blockers_with_line_and_text(self) -> None:
        doc = parse_handoff("# H\nBlocked: waiting for X.\nprose\n- Blocker: needs Y\n", "h.md")
        self.assertEqual([(b.line, b.text) for b in doc.blockers],
                         [(2, "waiting for X."), (4, "needs Y")])

    def test_parser_ignores_prose_with_blocked(self) -> None:
        doc = parse_handoff("The change was blocked by CI.\n", "h.md")
        self.assertEqual(doc.blockers, [])

    def test_parser_records_branch_and_head_lines(self) -> None:
        doc = parse_handoff("# H\nHEAD: abcdef1\nBranch: main\n", "h.md")
        self.assertEqual((doc.head_line, doc.branch_line), (2, 3))


if __name__ == "__main__":
    unittest.main()
