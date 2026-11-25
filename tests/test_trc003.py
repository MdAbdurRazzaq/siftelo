"""TRC-003 regressions: per-worktree configuration and the Git metadata trust boundary.

Written before the fix and run against APN-002 to establish RED. Every
"helper must not run" test uses a marker-writing helper in a disposable
synthetic repository; nothing outside the temporary directory is touched.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import exclude_from_status, git, head_of, make_repo, temp_dir, write

from siftelo import cli, gitinspect, preflight


def _script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


def _cmd(script: Path) -> str:
    # Forward slashes: git config files treat backslashes as escapes, which breaks Windows paths.
    return f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}"'


def _filter_helper(tmp: Path, marker: Path) -> str:
    """A clean filter that records it ran and passes content through unchanged."""
    script = _script(tmp / "filter_helper.py",
                     "import sys, pathlib\n"
                     f"pathlib.Path(r'{marker}').write_text('ran', encoding='utf-8')\n"
                     "sys.stdout.buffer.write(sys.stdin.buffer.read())\n")
    return _cmd(script)


def _fsmonitor_helper(tmp: Path, marker: Path) -> str:
    script = _script(tmp / "fsmonitor_helper.py",
                     f"import pathlib\npathlib.Path(r'{marker}').write_text('ran', encoding='utf-8')\n")
    return _cmd(script)


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.repo = make_repo(self.tmp, {"docs/a.md": "x\n"}, branch="main")
        self.head = head_of(self.repo)
        write(self.repo, "handoff.md", f"Branch: main\nHEAD: {self.head}\n")
        exclude_from_status(self.repo, "handoff.md")
        self.marker = self.tmp / "helper-ran.txt"

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def _enable_worktree_config(self, repo: Path) -> None:
        git(repo, "config", "core.repositoryformatversion", "1")
        git(repo, "config", "extensions.worktreeConfig", "true")

    def _commit_gitattributes(self, repo: Path) -> None:
        # Commit the attribute file before any filter is configured, so no filter runs during setup.
        write(repo, ".gitattributes", "*.md filter=probe\n")
        git(repo, "add", ".gitattributes")
        git(repo, "commit", "-q", "-m", "attributes")

    def _modify_same_length(self, repo: Path) -> None:
        # Same-length edit forces Git to hash the file, which is when a clean filter would run.
        write(repo, "docs/a.md", "Y\n")

    def _wt_status(self, report) -> list[str]:
        return [f.status for f in report.findings if f.subject == "working-tree"]


# --------------------------------------------------------------------------
# P1: per-worktree configuration (config.worktree) must not execute anything
# --------------------------------------------------------------------------
class WorktreeConfigBoundary(_Base):
    def test_worktree_config_clean_filter_never_runs(self) -> None:
        self._enable_worktree_config(self.repo)
        self._commit_gitattributes(self.repo)
        # The filter lives only in per-worktree config, which the local audit does not read.
        git(self.repo, "config", "--worktree", "filter.probe.clean", _filter_helper(self.tmp, self.marker))
        self._modify_same_length(self.repo)
        report = preflight.run_preflight(self.repo, "handoff.md")
        self.assertFalse(self.marker.exists(), "clean filter in config.worktree was executed")
        self.assertEqual(self._wt_status(report), ["unknown"])

    def test_worktree_config_fsmonitor_never_runs(self) -> None:
        self._enable_worktree_config(self.repo)
        git(self.repo, "config", "--worktree", "core.fsmonitor", _fsmonitor_helper(self.tmp, self.marker))
        preflight.run_preflight(self.repo, "handoff.md")
        self.assertFalse(self.marker.exists(), "fsmonitor helper in config.worktree was executed")

    def test_worktree_config_include_is_not_followed_or_executed(self) -> None:
        outside = self.tmp / "outside.cfg"
        outside.write_text(
            "[filter \"probe\"]\n"
            f"\tclean = {_filter_helper(self.tmp, self.marker)}\n",
            encoding="utf-8",
        )
        self._enable_worktree_config(self.repo)
        self._commit_gitattributes(self.repo)
        git(self.repo, "config", "--worktree", "include.path", outside.as_posix())
        self._modify_same_length(self.repo)
        report = preflight.run_preflight(self.repo, "handoff.md")
        self.assertFalse(self.marker.exists(), "filter reached through config.worktree include was executed")
        self.assertEqual(self._wt_status(report), ["unknown"])

    def test_enabled_worktree_config_skips_status_even_without_filters(self) -> None:
        self._enable_worktree_config(self.repo)
        report = preflight.run_preflight(self.repo, "handoff.md")
        self.assertFalse(report.repository.get("status_inspected"))
        self.assertIn("worktreeConfig", report.repository.get("status_skip_reason") or "")
        self.assertEqual(self._wt_status(report), ["unknown"])

    def test_config_worktree_file_alone_blocks_status(self) -> None:
        # The file is written directly, so it is present even though the extension is not enabled.
        write(self.repo, ".git/config.worktree", "[core]\n\tbare = false\n")
        report = preflight.run_preflight(self.repo, "handoff.md")
        self.assertFalse(report.repository.get("status_inspected"))
        self.assertEqual(self._wt_status(report), ["unknown"])

    def test_config_worktree_detected_when_path_contains_glob_characters(self) -> None:
        # Glob metacharacters in the repository path must not hide a per-worktree config file.
        bracketed = self.tmp / "dir[x]"  # '*' is not a legal Windows name; brackets are
        bracketed.mkdir()
        repo = make_repo(bracketed, {"a.md": "a\n"}, branch="main")
        write(repo, ".git/worktrees/w1/config.worktree", "[core]\n\tbare = false\n")
        write(repo, "handoff.md", f"Branch: main\nHEAD: {head_of(repo)}\n")
        report = preflight.run_preflight(repo, "handoff.md")
        self.assertFalse(report.repository.get("status_inspected"))

    def test_ordinary_repository_status_still_inspected(self) -> None:
        self._commit_gitattributes(self.repo)
        report = preflight.run_preflight(self.repo, "handoff.md")
        self.assertTrue(report.repository.get("status_inspected"))
        self.assertEqual(report.repository.get("status_skip_reason"), None)


# --------------------------------------------------------------------------
# P2: the boundary between project content and Git metadata outside the root
# --------------------------------------------------------------------------
class ExternalGitMetadataBoundary(_Base):
    def _linked_worktree(self) -> Path:
        wt = self.tmp / "wt"
        git(self.repo, "worktree", "add", "-q", "-b", "wtb", str(wt))
        write(wt, "handoff.md", f"Branch: wtb\nHEAD: {head_of(wt)}\n")
        return wt

    def test_upward_discovery_is_disabled(self) -> None:
        child = self.repo / "docs"
        write(child, "handoff.md", f"Branch: main\nHEAD: {self.head}\n")
        report = preflight.run_preflight(child, "handoff.md")
        self.assertFalse(report.repository.get("is_repo"),
                         "project root without its own .git discovered an enclosing repository")
        self.assertEqual(report.exit_code(), 3)

    def test_linked_worktree_fails_closed_by_default(self) -> None:
        wt = self._linked_worktree()
        report = preflight.run_preflight(wt, "handoff.md")
        self.assertFalse(report.repository.get("status_inspected"))
        self.assertIn("outside the project root", report.repository.get("blocked_reason") or "")
        boundary = [f for f in report.findings if f.subject == "git-metadata"]
        self.assertEqual([f.status for f in boundary], ["unknown"])
        self.assertEqual(report.exit_code(), 3)

    def test_linked_worktree_runs_with_explicit_approval(self) -> None:
        wt = self._linked_worktree()
        report = preflight.run_preflight(wt, "handoff.md", allow_external_git_metadata=True)
        self.assertTrue(report.repository.get("status_inspected"))
        self.assertEqual(report.errors, [])

    def test_separate_git_dir_fails_closed_by_default(self) -> None:
        sep_root = self.tmp / "sep"
        sep_meta = self.tmp / "sep-meta"
        sep_root.mkdir()
        git(sep_root, "init", "-q", "-b", "main", f"--separate-git-dir={sep_meta}")
        write(sep_root, "a.txt", "a\n")
        git(sep_root, "add", "a.txt")
        git(sep_root, "-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-q", "-m", "b")
        write(sep_root, "handoff.md", f"Branch: main\nHEAD: {head_of(sep_root)}\n")
        report = preflight.run_preflight(sep_root, "handoff.md")
        self.assertFalse(report.repository.get("status_inspected"))
        self.assertEqual(report.exit_code(), 3)

    def test_approved_external_metadata_still_audited_for_filters(self) -> None:
        # Attributes are committed before the worktree branch is created, so the linked worktree has them.
        self._commit_gitattributes(self.repo)
        wt = self._linked_worktree()
        # The filter sits in the shared (external) config and is reached through a linked worktree.
        git(self.repo, "config", "filter.probe.clean", _filter_helper(self.tmp, self.marker))
        write(wt, "docs/a.md", "Y\n")
        report = preflight.run_preflight(wt, "handoff.md", allow_external_git_metadata=True)
        self.assertFalse(self.marker.exists(), "approved external config filter was executed")
        self.assertEqual(self._wt_status(report), ["unknown"])

    def test_alternates_file_is_external_metadata(self) -> None:
        other = make_repo(self.tmp / "other", {"x.txt": "x\n"}, branch="main")
        objects = other / ".git" / "objects"
        alt = self.repo / ".git" / "objects" / "info" / "alternates"
        alt.parent.mkdir(parents=True, exist_ok=True)
        alt.write_text(str(objects) + "\n", encoding="utf-8", newline="\n")
        report = preflight.run_preflight(self.repo, "handoff.md")
        self.assertFalse(report.repository.get("status_inspected"))
        self.assertEqual(report.exit_code(), 3)


# --------------------------------------------------------------------------
# P3: every Git invocation carries the boundary, and the CLI exposes approval
# --------------------------------------------------------------------------
class InvocationBoundary(_Base):
    def test_every_git_call_has_discovery_ceiling_and_neutralisers(self) -> None:
        recorded: list[tuple[list[str], dict]] = []
        real_run = gitinspect.run_bounded  # TRC-010: the single chokepoint for every Git call

        def spy(argv, **kwargs):
            recorded.append((list(argv), dict(kwargs.get("env") or {})))
            return real_run(argv, **kwargs)

        with mock.patch.object(gitinspect, "run_bounded", side_effect=spy):
            gitinspect.inspect_repository(self.repo)
        self.assertTrue(recorded)
        for argv, env in recorded:
            self.assertIn("core.fsmonitor=false", argv)
            self.assertEqual(env.get("GIT_CEILING_DIRECTORIES"), os.path.realpath(self.repo.parent))
            self.assertEqual(env.get("GIT_CONFIG_NOSYSTEM"), "1")
            self.assertNotIn("GIT_DIR", env)

    def test_cli_exposes_explicit_external_metadata_approval(self) -> None:
        wt = self.tmp / "wt"
        git(self.repo, "worktree", "add", "-q", "-b", "wtc", str(wt))
        write(wt, "handoff.md", f"Branch: wtc\nHEAD: {head_of(wt)}\n")
        default_out, approved_out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(default_out):
            cli.main(["--project-root", str(wt), "--handoff", "handoff.md", "--format", "json"])
        with contextlib.redirect_stdout(approved_out):
            code = cli.main(["--project-root", str(wt), "--handoff", "handoff.md", "--format", "json",
                             "--allow-external-git-metadata"])
        self.assertFalse(json.loads(default_out.getvalue())["repository"].get("status_inspected"))
        self.assertTrue(json.loads(approved_out.getvalue())["repository"].get("status_inspected"))
        self.assertNotEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
