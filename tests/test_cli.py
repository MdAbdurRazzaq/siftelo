"""CLI behaviour: exit codes, output formats, and read-only guarantees."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path

from helpers import exclude_from_status, git, head_of, make_repo, temp_dir, write

from siftelo import cli


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.repo = make_repo(self.tmp, {"docs/a.md": "a\n"}, branch="main")
        self.head = head_of(self.repo)
        write(self.repo, "handoff.md", f"Branch: main\nHEAD: {self.head}\n")
        exclude_from_status(self.repo, "handoff.md")

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def _run(self, *extra: str) -> tuple[int, str]:
        buf = io.StringIO()
        argv = ["--project-root", str(self.repo), "--handoff", "handoff.md", *extra]
        with contextlib.redirect_stdout(buf):
            code = cli.main(argv)
        return code, buf.getvalue()

    def test_correct_state_exit_zero_json(self) -> None:
        code, out = self._run("--format", "json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(data["summary"]["stale"], 0)
        self.assertEqual(data["repository"]["head"], self.head)

    def test_stale_state_exit_one(self) -> None:
        write(self.repo, "docs/a.md", "changed\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "next")
        code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("[stale]", out)

    def test_report_goes_to_stdout_and_repo_untouched(self) -> None:
        before = git(self.repo, "rev-parse", "HEAD")
        status_before = git(self.repo, "status", "--porcelain")
        code, out = self._run()
        self.assertIn("# Siftelo Handoff Preflight", out)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertEqual(git(self.repo, "status", "--porcelain"), status_before)

    def test_manifest_error_exit_two(self) -> None:
        write(self.repo, "manifest.json", "{not json")
        code, out = self._run("--manifest", "manifest.json")
        self.assertEqual(code, 2)
        self.assertIn("manifest rejected", out)

    def test_handoff_bytes_unchanged_by_run(self) -> None:
        digest = hashlib.sha256((self.repo / "handoff.md").read_bytes()).hexdigest()
        self._run("--format", "json")
        self.assertEqual(hashlib.sha256((self.repo / "handoff.md").read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
