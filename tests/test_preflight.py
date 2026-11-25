"""The twelve required behaviours, exercised on temporary synthetic Git repositories."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from helpers import can_symlink, exclude_from_status, head_of, make_repo, temp_dir, write, git

from siftelo import gitinspect, preflight
from siftelo.report import to_json


def handoff_text(branch: str, head: str, extra: str = "") -> str:
    return (
        "# Handoff\n\n"
        f"Branch: {branch}\n"
        f"HEAD: {head}\n\n"
        "## Status\n\nStopped at step 3.\n"
        f"{extra}"
    )


def statuses(report) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in report.findings:
        out.setdefault(f.status, []).append(f"{f.category}:{f.subject}")
    return out


class PreflightCases(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.repo = make_repo(self.tmp, {"docs/notes.md": "notes v1\n"}, branch="feature/x")
        self.head = head_of(self.repo)

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def _handoff(self, text: str, name: str = "handoff.md") -> str:
        write(self.repo, name, text)
        exclude_from_status(self.repo, name, "manifest.json")
        return name

    def _manifest(self, data: dict) -> str:
        write(self.repo, "manifest.json", json.dumps(data))
        return "manifest.json"

    # 1. matching repository SHA and branch
    def test_01_matching_sha_and_branch_verified(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head))
        report = preflight.run_preflight(self.repo, h)
        s = statuses(report)
        self.assertNotIn("stale", s)
        self.assertIn("repository:head", s["verified_metadata"])
        self.assertIn("repository:branch", s["verified_metadata"])
        self.assertEqual(report.exit_code(), 0)

    # 2. stale HEAD
    def test_02_stale_head_reported(self) -> None:
        old = self.head
        write(self.repo, "docs/notes.md", "notes v2\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "moved on")
        self.assertNotEqual(old, head_of(self.repo))
        h = self._handoff(handoff_text("feature/x", old))
        report = preflight.run_preflight(self.repo, h)
        stale = [f for f in report.findings if f.status == "stale" and f.category == "repository"]
        self.assertTrue(any("expects" in f.message and "HEAD is" in f.message for f in stale))
        self.assertEqual(report.exit_code(), 1)

    # 3. wrong branch
    def test_03_wrong_branch_reported(self) -> None:
        h = self._handoff(handoff_text("main", self.head))
        report = preflight.run_preflight(self.repo, h)
        branch = [f for f in report.findings if f.subject == "branch"]
        self.assertEqual([f.status for f in branch], ["stale"])
        self.assertIn("feature/x", branch[0].message)
        self.assertEqual(report.exit_code(), 1)

    # 4. missing evidence file
    def test_04_missing_evidence_file_is_stale(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head, "\n## Evidence\n\n- `reports/missing.json`\n"))
        report = preflight.run_preflight(self.repo, h)
        missing = [f for f in report.findings if f.category == "reference" and f.subject == "reports/missing.json"]
        self.assertEqual([f.status for f in missing], ["stale"])
        self.assertEqual(report.exit_code(), 1)

    def test_04b_missing_manifest_evidence_is_stale(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head))
        m = self._manifest({"schema_version": 1,
                            "evidence": [{"path": "reports/none.json", "sha256": "0" * 64}]})
        report = preflight.run_preflight(self.repo, h, m)
        ev = [f for f in report.findings if f.category == "evidence"]
        self.assertEqual([f.status for f in ev], ["stale"])
        self.assertIn("missing", ev[0].message)

    # 5. mismatched file hash
    def test_05_hash_mismatch_is_stale(self) -> None:
        import hashlib
        evidence = write(self.repo, "reports/run.txt", "original\n")
        recorded = hashlib.sha256(evidence.read_bytes()).hexdigest()
        evidence.write_text("tampered\n", encoding="utf-8", newline="\n")
        h = self._handoff(handoff_text("feature/x", self.head))
        m = self._manifest({"schema_version": 1,
                            "evidence": [{"path": "reports/run.txt", "sha256": recorded}]})
        report = preflight.run_preflight(self.repo, h, m)
        ev = [f for f in report.findings if f.category == "evidence"]
        self.assertEqual([f.status for f in ev], ["stale"])
        self.assertIn("mismatch", ev[0].message)

    def test_05b_hash_match_is_verified(self) -> None:
        import hashlib
        evidence = write(self.repo, "reports/run.txt", "original\n")
        recorded = hashlib.sha256(evidence.read_bytes()).hexdigest()
        h = self._handoff(handoff_text("feature/x", self.head))
        m = self._manifest({"schema_version": 1,
                            "evidence": [{"path": "reports/run.txt", "sha256": recorded}]})
        report = preflight.run_preflight(self.repo, h, m)
        ev = [f for f in report.findings if f.category == "evidence"]
        self.assertEqual([f.status for f in ev], ["verified_metadata"])

    # 6. unverified test-success claim
    def test_06_test_success_claim_never_verified(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head, "\nAll tests pass on my machine.\n"))
        m = self._manifest({"schema_version": 1,
                            "claims": [{"id": "t1", "text": "suite is green", "status": "agent_reported"}]})
        report = preflight.run_preflight(self.repo, h, m)
        claims = [f for f in report.findings if f.category == "claim"]
        self.assertTrue(claims)
        self.assertTrue(all(f.status == "agent_reported" for f in claims))
        self.assertFalse(any(f.status == "verified_metadata" and f.category == "claim" for f in report.findings))
        self.assertIn("not executed or verified", claims[0].message)

    def test_06b_manifest_cannot_upgrade_claim_to_verified(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head))
        m = self._manifest({"schema_version": 1,
                            "claims": [{"id": "t1", "text": "tests green", "status": "verified_metadata"}]})
        report = preflight.run_preflight(self.repo, h, m)
        claim = [f for f in report.findings if f.category == "claim"][0]
        self.assertEqual(claim.status, "unknown")

    # 7. missing publication approval
    def test_07_pending_publication_approval_reported(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head,
                                       "\nPending approval: publish branch publicly.\n"))
        m = self._manifest({"schema_version": 1,
                            "approvals": [{"id": "publication", "status": "pending",
                                           "description": "Publish branch"}]})
        report = preflight.run_preflight(self.repo, h, m)
        approvals = [f for f in report.findings if f.category == "approval"]
        self.assertTrue(approvals)
        self.assertTrue(all(f.status == "unknown" for f in approvals))

    def test_07b_publication_mentioned_without_any_record(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head,
                                       "\nPending approval: publish the summary publicly.\n"))
        report = preflight.run_preflight(self.repo, h)
        msgs = [f.message for f in report.findings if f.subject == "publication"]
        self.assertEqual(len(msgs), 1)
        self.assertIn("records none", msgs[0])

    # 8. malformed JSON manifest
    def test_08_malformed_manifest_is_error_exit_2(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head))
        write(self.repo, "manifest.json", '{"schema_version": 1, "evidence": [}')
        report = preflight.run_preflight(self.repo, h, "manifest.json")
        self.assertEqual(len(report.errors), 1)
        self.assertIn("malformed JSON", report.errors[0])
        self.assertEqual(report.findings, [])
        self.assertEqual(report.exit_code(), 2)

    def test_08b_unknown_manifest_key_rejected(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head))
        m = self._manifest({"schema_version": 1, "evidnce": []})
        report = preflight.run_preflight(self.repo, h, m)
        self.assertIn("unknown fields", report.errors[0])

    # 9. path traversal rejection
    def test_09_traversal_in_handoff_reference_rejected(self) -> None:
        secret = self.tmp / "outside-secret.txt"
        secret.write_text("do not read\n", encoding="utf-8")
        h = self._handoff(handoff_text("feature/x", self.head,
                                       "\n## Evidence\n\n- `../outside-secret.txt`\n"))
        report = preflight.run_preflight(self.repo, h)
        rejected = [f for f in report.findings if f.status == "rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertIn("traversal", rejected[0].message)
        self.assertEqual(report.exit_code(), 1)

    def test_09b_traversal_in_manifest_evidence_rejected(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head))
        m = self._manifest({"schema_version": 1,
                            "evidence": [{"path": "../../etc/passwd", "sha256": "0" * 64}]})
        report = preflight.run_preflight(self.repo, h, m)
        self.assertEqual([f.status for f in report.findings if f.category == "evidence"], ["rejected"])

    def test_09c_handoff_outside_root_refused(self) -> None:
        outside = self.tmp / "elsewhere.md"
        outside.write_text(handoff_text("feature/x", self.head), encoding="utf-8")
        report = preflight.run_preflight(self.repo, outside)
        self.assertTrue(report.errors)
        self.assertIn("inside the project root", report.errors[0])

    def test_09d_absolute_evidence_path_rejected(self) -> None:
        h = self._handoff(handoff_text("feature/x", self.head))
        absolute = str((self.tmp / "outside-secret.txt").resolve())
        m = self._manifest({"schema_version": 1, "evidence": [{"path": absolute}]})
        report = preflight.run_preflight(self.repo, h, m)
        self.assertEqual([f.status for f in report.findings if f.category == "evidence"], ["rejected"])

    # 10. symlink escape rejection
    def test_10_symlink_escape_rejected(self) -> None:
        if not can_symlink(self.tmp):
            self.skipTest("symlink creation not permitted on this platform/account")
        outside = self.tmp / "outside-target.txt"
        outside.write_text("secret\n", encoding="utf-8")
        link = self.repo / "docs" / "escape.txt"
        os.symlink(outside, link)
        h = self._handoff(handoff_text("feature/x", self.head,
                                       "\n## Evidence\n\n- `docs/escape.txt`\n"))
        report = preflight.run_preflight(self.repo, h)
        rejected = [f for f in report.findings if f.status == "rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertIn("symlink escape", rejected[0].message)

    def test_10b_symlinked_directory_escape_rejected(self) -> None:
        if not can_symlink(self.tmp):
            self.skipTest("symlink creation not permitted on this platform/account")
        outside_dir = self.tmp / "outside-dir"
        outside_dir.mkdir()
        (outside_dir / "data.txt").write_text("x", encoding="utf-8")
        os.symlink(outside_dir, self.repo / "linkdir", target_is_directory=True)
        h = self._handoff(handoff_text("feature/x", self.head))
        m = self._manifest({"schema_version": 1, "evidence": [{"path": "linkdir/data.txt"}]})
        report = preflight.run_preflight(self.repo, h, m)
        self.assertEqual([f.status for f in report.findings if f.category == "evidence"], ["rejected"])

    # 11. deterministic report ordering
    def test_11_report_is_deterministic(self) -> None:
        h = self._handoff(handoff_text("main", "deadbeef" * 5, "\n## Evidence\n\n- `zz/none.md`\n- `aa/none.md`\n"
                                       "\nAll tests pass.\n\nPending approval: publish.\n"))
        m = self._manifest({"schema_version": 1, "approvals": [{"id": "publication", "status": "pending"}]})
        first = to_json(preflight.run_preflight(self.repo, h, m))
        second = to_json(preflight.run_preflight(self.repo, h, m))
        self.assertEqual(first, second)
        report = preflight.run_preflight(self.repo, h, m)
        keys = [f.sort_key() for f in report.findings]
        self.assertEqual(keys, sorted(keys))
        ranks = [preflight.STATUS_ORDER[f.status] for f in report.findings]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(report.findings[0].status, "stale")

    # 12. bounded output and unknown-state handling
    def test_12_detached_head_is_unknown_not_stale(self) -> None:
        git(self.repo, "checkout", "-q", "--detach")
        h = self._handoff(handoff_text("feature/x", self.head))
        report = preflight.run_preflight(self.repo, h)
        branch = [f for f in report.findings if f.subject == "branch"]
        self.assertEqual([f.status for f in branch], ["unknown"])

    def test_12b_not_a_git_repository_is_unknown(self) -> None:
        # Stop git from discovering a parent repository above the temp directory.
        plain = self.tmp / "plain"
        plain.mkdir()
        (plain / "handoff.md").write_text(handoff_text("main", "abc1234"), encoding="utf-8")
        saved = os.environ.get("GIT_CEILING_DIRECTORIES")
        os.environ["GIT_CEILING_DIRECTORIES"] = str(self.tmp)
        try:
            report = preflight.run_preflight(plain, "handoff.md")
        finally:
            if saved is None:
                os.environ.pop("GIT_CEILING_DIRECTORIES", None)
            else:
                os.environ["GIT_CEILING_DIRECTORIES"] = saved
        self.assertEqual(report.repository["is_repo"], False)
        self.assertEqual(report.findings[0].status, "unknown")
        # Not inspectable is not "no contradiction": it requires review (exit 3).
        self.assertEqual(report.exit_code(), 3)

    def test_12f_root_inside_larger_repository_is_not_discovered(self) -> None:
        # TRC-003: upward discovery is disabled. A folder without its own .git is not
        # attached to an enclosing repository, so no revision claim is made about it.
        sub = self.repo / "docs"
        (sub / "handoff.md").write_text(handoff_text("feature/x", self.head), encoding="utf-8")
        report = preflight.run_preflight(sub, "handoff.md")
        self.assertFalse(report.repository.get("is_repo"))
        git_notes = [f for f in report.findings if f.subject == "git"]
        self.assertEqual([f.status for f in git_notes], ["unknown"])
        self.assertEqual(report.exit_code(), 3)

    def test_12c_changed_files_bounded(self) -> None:
        for i in range(gitinspect.MAX_CHANGED_FILES_REPORTED + 25):
            write(self.repo, f"scratch/f{i:04d}.txt", "x\n")
        h = self._handoff(handoff_text("feature/x", self.head))
        report = preflight.run_preflight(self.repo, h)
        self.assertEqual(len(report.repository["changed_files"]), gitinspect.MAX_CHANGED_FILES_REPORTED)
        self.assertTrue(report.repository["changed_files_truncated"])

    def test_12d_findings_bounded(self) -> None:
        original = preflight.MAX_FINDINGS
        preflight.MAX_FINDINGS = 3
        try:
            refs = "".join(f"- `missing/{i}.md`\n" for i in range(10))
            h = self._handoff(handoff_text("feature/x", self.head, "\n## Evidence\n\n" + refs))
            report = preflight.run_preflight(self.repo, h)
            self.assertEqual(len(report.findings), 3)
            self.assertTrue(report.truncated)
        finally:
            preflight.MAX_FINDINGS = original

    def test_12e_unknown_when_no_expected_revision(self) -> None:
        h = self._handoff("# Handoff with no metadata\n\nNothing recorded.\n")
        report = preflight.run_preflight(self.repo, h)
        head = [f for f in report.findings if f.subject == "head"]
        self.assertEqual([f.status for f in head], ["unknown"])


if __name__ == "__main__":
    unittest.main()
