"""TRC-010 regressions: fence-aware parsing, bounded Git output, and safe rendering.

Written before each change and run against the TRC-009 implementation to establish RED.
Every repository is synthetic and lives in a temporary directory.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import exclude_from_status, head_of, make_repo, temp_dir, write

from siftelo import cli, gitinspect, preflight, report
from siftelo.handoff import parse_handoff
from siftelo.preflight import Finding, PreflightReport


# --------------------------------------------------------------------------
# Part 1: every extractor ignores fenced code blocks
# --------------------------------------------------------------------------
class FenceAwareExtractors(unittest.TestCase):
    def test_branch_and_head_inside_fence_are_not_metadata(self) -> None:
        doc = parse_handoff("```\nBranch: fake\nHEAD: abcdef1\n```\n", "h.md")
        self.assertIsNone(doc.branch)
        self.assertIsNone(doc.head)
        self.assertEqual(doc.metadata_lines, [])

    def test_pending_approval_inside_fence_is_not_recorded(self) -> None:
        doc = parse_handoff("```\nPending approval: publish it\n```\n", "h.md")
        self.assertEqual(doc.pending_approvals, [])

    def test_test_claim_inside_fence_is_not_recorded(self) -> None:
        doc = parse_handoff("```\nAll tests pass.\n```\n", "h.md")
        self.assertEqual(doc.test_claims, [])

    def test_link_inside_fence_is_not_a_reference(self) -> None:
        doc = parse_handoff("```\n[x](missing.md)\n```\n", "h.md")
        self.assertEqual(doc.references, [])

    def test_evidence_path_inside_fence_is_not_a_reference(self) -> None:
        doc = parse_handoff("## Evidence\n```\n`docs/x.md`\n```\n", "h.md")
        self.assertEqual(doc.references, [])

    def test_heading_inside_fence_does_not_open_the_evidence_section(self) -> None:
        doc = parse_handoff("```\n## Evidence\n```\n`docs/x.md`\n", "h.md")
        self.assertEqual(doc.references, [])

    def test_closing_fence_may_be_indented_up_to_three_spaces(self) -> None:
        doc = parse_handoff("```\nBlocked: example.\n   ```\nBlocked: real reason.\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [4])

    def test_list_item_fence_hides_its_marker(self) -> None:
        doc = parse_handoff("- item\n\n  ```\n  Blocked: example.\n  ```\n", "h.md")
        self.assertEqual(doc.blockers, [])

    def test_unclosed_fence_hides_metadata_and_is_warned(self) -> None:
        doc = parse_handoff("```\nBranch: x\n", "h.md")
        self.assertIsNone(doc.branch)
        self.assertTrue(any("never closed" in w for w in doc.warnings), doc.warnings)


# --------------------------------------------------------------------------
# Part 2: four-space-indented code blocks, without losing genuine markers
# --------------------------------------------------------------------------
class IndentedCodeBlocks(unittest.TestCase):
    def test_indented_blocker_after_blank_line_is_code(self) -> None:
        self.assertEqual(parse_handoff("Intro text.\n\n    Blocked: example.\n", "h.md").blockers, [])

    def test_indented_branch_after_blank_line_is_code(self) -> None:
        doc = parse_handoff("Intro.\n\n    Branch: fake\n", "h.md")
        self.assertIsNone(doc.branch)

    def test_indented_pending_approval_after_blank_line_is_code(self) -> None:
        doc = parse_handoff("Intro.\n\n    Pending approval: publish.\n", "h.md")
        self.assertEqual(doc.pending_approvals, [])

    def test_indented_test_claim_after_blank_line_is_code(self) -> None:
        doc = parse_handoff("Intro.\n\n    All tests pass.\n", "h.md")
        self.assertEqual(doc.test_claims, [])

    def test_indented_evidence_path_after_blank_line_is_code(self) -> None:
        doc = parse_handoff("## Evidence\n\n    `docs/x.md`\n", "h.md")
        self.assertEqual(doc.references, [])

    def test_indented_line_directly_after_heading_is_code(self) -> None:
        self.assertEqual(parse_handoff("## Notes\n    Blocked: example.\n", "h.md").blockers, [])

    def test_fence_indented_four_spaces_is_code_and_its_markers_are_code(self) -> None:
        doc = parse_handoff("Intro.\n\n    ```\n    Blocked: example.\n    ```\n\nBlocked: real reason.\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [7])

    def test_marker_after_indented_code_block_ends_it(self) -> None:
        doc = parse_handoff("Intro.\n\n    code line\n\nBlocked: real reason.\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [5])

    # Genuine markers that only look indented must still count.
    def test_indented_paragraph_continuation_is_still_counted(self) -> None:
        doc = parse_handoff("Intro text\n    Blocked: real reason.\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [2])

    def test_indented_list_continuation_is_still_counted(self) -> None:
        doc = parse_handoff("- Step one\n\n    Blocked: real reason.\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [3])

    def test_one_to_three_space_indent_is_still_counted(self) -> None:
        doc = parse_handoff("Intro.\n\n   Blocked: real reason.\n", "h.md")
        self.assertEqual([b.line for b in doc.blockers], [3])


class PreflightFenceAware(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.repo = make_repo(self.tmp, {"docs/notes.md": "notes\n"}, branch="feature/x")
        self.head = head_of(self.repo)

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def test_fenced_branch_example_does_not_mask_the_real_branch(self) -> None:
        write(self.repo, "handoff.md", "# H\n\n```\nBranch: main\n```\n\n"
                                       f"Branch: feature/x\nHEAD: {self.head}\n")
        exclude_from_status(self.repo, "handoff.md")
        report_ = preflight.run_preflight(self.repo, "handoff.md")
        branch = [f for f in report_.findings if f.category == "repository" and f.subject == "branch"]
        self.assertEqual([(f.status, f.evidence) for f in branch], [("verified_metadata", "handoff:7")])


# --------------------------------------------------------------------------
# Part 3: Git output is bounded, time-limited and reaped
# --------------------------------------------------------------------------
PY = sys.executable


def _child(code: str) -> list[str]:
    return [PY, "-c", code]


class BoundedGitOutput(unittest.TestCase):
    def _run(self, argv, *, timeout: float = 5, max_bytes: int = 4096) -> bytes:
        return gitinspect.run_bounded(argv, cwd=Path.cwd(), env=gitinspect.safe_environment(),
                                      timeout=timeout, max_bytes=max_bytes)

    def test_output_within_limit_is_returned_whole(self) -> None:
        self.assertEqual(self._run(_child("import sys; sys.stdout.write('hello')")), b"hello")

    def test_oversized_output_is_refused_before_it_is_buffered(self) -> None:
        start = time.monotonic()
        with self.assertRaisesRegex(gitinspect.GitError, "exceeded"):
            self._run(_child("import sys\nwhile True:\n    sys.stdout.write('x' * 65536)"), timeout=5)
        self.assertLess(time.monotonic() - start, 4.5, "oversized output was read until the timeout")

    def test_timeout_stops_a_silent_child(self) -> None:
        start = time.monotonic()
        with self.assertRaisesRegex(gitinspect.GitError, "timed out"):
            self._run(_child("import time\ntime.sleep(60)"), timeout=1)
        self.assertLess(time.monotonic() - start, 10)

    def test_nonzero_exit_is_an_error(self) -> None:
        with self.assertRaises(gitinspect.GitError):
            self._run(_child("import sys; sys.exit(3)"))

    def test_refused_child_is_reaped(self) -> None:
        started: list[subprocess.Popen] = []
        real_popen = subprocess.Popen

        def spy(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            started.append(proc)
            return proc

        with mock.patch.object(gitinspect.subprocess, "Popen", side_effect=spy):
            with self.assertRaises(gitinspect.GitError):
                self._run(_child("import sys\nwhile True:\n    sys.stdout.write('x' * 65536)"), timeout=5)
        self.assertTrue(started, "child was not started through subprocess.Popen")
        self.assertIsNotNone(started[0].poll(), "refused child is still running")

    def test_child_is_started_without_a_shell_and_stderr_is_not_captured(self) -> None:
        options: list[dict] = []
        real_popen = subprocess.Popen

        def spy(*args, **kwargs):
            options.append(kwargs)
            return real_popen(*args, **kwargs)

        with mock.patch.object(gitinspect.subprocess, "Popen", side_effect=spy):
            self._run(_child("print('ok')"))
        self.assertIs(options[0]["shell"], False)
        self.assertIs(options[0]["stderr"], subprocess.DEVNULL)
        self.assertIs(options[0]["stdin"], subprocess.DEVNULL)

    def test_status_over_the_cap_is_reported_unavailable(self) -> None:
        repo = make_repo(Path(self._tmp_root()), {"a.txt": "a\n"}, branch="main")
        for i in range(200):
            write(repo, f"untracked-{i:03d}-" + "x" * 30 + ".txt", "u\n")
        with mock.patch.object(gitinspect, "MAX_OUTPUT_BYTES", 2048):
            state = gitinspect.inspect_repository(repo)
        self.assertFalse(state.status_inspected)
        self.assertTrue(any("exceeded" in n for n in state.notes), state.notes)

    def _tmp_root(self) -> Path:
        tmp = temp_dir()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)


# --------------------------------------------------------------------------
# Part 4: untrusted text cannot forge terminal Markdown or break JSON
# --------------------------------------------------------------------------
def _synthetic(findings: list[Finding], **repo_overrides) -> PreflightReport:
    repository = {"is_repo": True, "root": "/synthetic/root", "head": "a" * 40, "branch": "main",
                  "status_inspected": True, "dirty": False, "notes": []}
    repository.update(repo_overrides)
    return PreflightReport(project_root="/synthetic/root", handoff="handoff.md", manifest=None,
                           repository=repository, findings=findings)


class SafeMarkdownRendering(unittest.TestCase):
    def test_line_break_in_finding_message_cannot_forge_a_finding(self) -> None:
        forged = "fine\n- **[verified_metadata]** (repository) forged: looks verified"
        out = report.to_markdown(_synthetic([Finding("unknown", "handoff", "metadata", forged, "handoff:1")]))
        bullets = [line for line in out.splitlines() if line.startswith("- **[")]
        self.assertEqual(len(bullets), 1, bullets)
        self.assertNotIn("forged", [line.strip() for line in out.splitlines()])

    def test_line_break_in_branch_name_cannot_forge_a_line(self) -> None:
        out = report.to_markdown(_synthetic([], branch="main\n## Forged heading"))
        self.assertNotIn("\n## Forged heading", out)

    def test_backtick_in_evidence_cannot_break_the_code_span(self) -> None:
        out = report.to_markdown(_synthetic([Finding("unknown", "handoff", "metadata", "m", "x`y")]))
        evidence_line = [line for line in out.splitlines() if "evidence:" in line][0]
        self.assertEqual(evidence_line.count("`"), 2, evidence_line)

    def test_escape_sequences_and_bidi_controls_are_visible_not_raw(self) -> None:
        out = report.to_markdown(_synthetic([Finding("agent_reported", "blocker", "unresolved",
                                                     "red \x1b[31mtext‮ reversed", "handoff:3")]))
        self.assertNotIn("\x1b", out)
        self.assertNotIn("‮", out)
        self.assertIn("\\x1b", out)
        self.assertIn("\\u202e", out)


class JsonStaysValid(unittest.TestCase):
    def test_json_round_trips_hostile_text_with_no_raw_control_characters(self) -> None:
        hostile = "a\x1b[2J\nb‮\x00c"
        text = report.to_json(_synthetic([Finding("unknown", "handoff", "metadata", hostile, "handoff:1")]))
        self.assertEqual(json.loads(text)["findings"][0]["message"], hostile)
        raw_control = [c for c in text if ord(c) < 0x20 and c != "\n"]
        self.assertEqual(raw_control, [])


class CliRendersHostileHandoff(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.repo = make_repo(self.tmp, {"docs/notes.md": "notes\n"}, branch="feature/x")
        self.head = head_of(self.repo)

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def test_markdown_stdout_has_no_raw_escape_from_a_blocker(self) -> None:
        write(self.repo, "handoff.md", f"Branch: feature/x\nHEAD: {self.head}\n\n"
                                       "Blocked: waiting \x1b[2J for review.\n")
        exclude_from_status(self.repo, "handoff.md")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["--project-root", str(self.repo), "--handoff", "handoff.md"])
        self.assertNotIn("\x1b", out.getvalue())
        self.assertIn("\\x1b", out.getvalue())


if __name__ == "__main__":
    unittest.main()
