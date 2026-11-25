"""Regression tests for the independent-review corrections (TRC-002).

Each class maps to one review finding. These tests were written before the
fixes and were run against the APN-001 implementation to establish RED.
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

from helpers import can_symlink, exclude_from_status, git, head_of, make_repo, temp_dir, write

from siftelo import cli, gitinspect, preflight
from siftelo.manifest import ManifestError, parse_manifest_text
from siftelo.paths import PathSafetyError, resolve_within
from siftelo.report import to_dict


def _helper_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


def _command_for(script: Path) -> str:
    return f'"{sys.executable}" "{script}"'


# --------------------------------------------------------------------------
# Finding 1: Git configuration can execute external helpers
# --------------------------------------------------------------------------
class GitExecutionSafety(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.repo = make_repo(self.tmp, {"docs/notes.md": "notes\n"}, branch="main")
        self.head = head_of(self.repo)
        write(self.repo, "handoff.md", f"Branch: main\nHEAD: {self.head}\n")
        exclude_from_status(self.repo, "handoff.md")
        self.saved_env = {k: os.environ.get(k) for k in ("GIT_DIR", "GIT_WORK_TREE")}

    def tearDown(self) -> None:
        for k, v in self.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.__exit__(None, None, None)

    def test_fsmonitor_helper_in_repo_config_never_runs(self) -> None:
        marker = self.tmp / "fsmonitor-ran.txt"
        helper = _helper_script(self.tmp / "fsmonitor_helper.py",
                                f"import pathlib\npathlib.Path(r'{marker}').write_text('ran')\n")
        git(self.repo, "config", "core.fsmonitor", _command_for(helper))
        preflight.run_preflight(self.repo, "handoff.md")
        self.assertFalse(marker.exists(), "core.fsmonitor helper from repository config was executed")

    def test_clean_filter_in_local_config_never_runs_and_status_is_unknown(self) -> None:
        marker = self.tmp / "filter-ran.txt"
        helper = _helper_script(
            self.tmp / "filter_helper.py",
            "import sys, pathlib\n"
            f"pathlib.Path(r'{marker}').write_text('ran')\n"
            "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
        )
        write(self.repo, ".gitattributes", "*.md filter=probe\n")
        git(self.repo, "add", ".gitattributes")
        git(self.repo, "commit", "-q", "-m", "attributes")
        git(self.repo, "config", "filter.probe.clean", _command_for(helper))
        # Same-length edit forces Git to hash the file, which is when a clean filter would run.
        write(self.repo, "docs/notes.md", "NOTES\n")
        report = preflight.run_preflight(self.repo, "handoff.md")
        self.assertFalse(marker.exists(), "clean filter from repository config was executed")
        wt = [f for f in report.findings if f.subject == "working-tree"]
        self.assertEqual([f.status for f in wt], ["unknown"])
        self.assertIn("not inspected", wt[0].message)

    def test_status_is_called_with_neutralising_options(self) -> None:
        recorded: list[list[str]] = []
        real_run = gitinspect.run_bounded  # TRC-010: the single chokepoint for every Git call

        def spy(argv, **kwargs):
            recorded.append(list(argv))
            self.assertIsNotNone(kwargs.get("timeout"))
            return real_run(argv, **kwargs)

        with mock.patch.object(gitinspect, "run_bounded", side_effect=spy):
            gitinspect.inspect_repository(self.repo)
        self.assertTrue(recorded, "no git commands were recorded")
        for argv in recorded:
            self.assertEqual(argv[0], "git")
            self.assertIn("core.fsmonitor=false", argv, f"missing fsmonitor override: {argv}")
        status = [a for a in recorded if "status" in a]
        self.assertTrue(status)
        self.assertIn("--ignore-submodules=all", status[0])

    def test_git_dir_environment_cannot_redirect_inspection(self) -> None:
        other_root = self.tmp / "other"
        other_root.mkdir()
        other = make_repo(other_root, {"x.txt": "other\n"}, branch="main")
        os.environ["GIT_DIR"] = str(other / ".git")
        os.environ["GIT_WORK_TREE"] = str(other)
        report = preflight.run_preflight(self.repo, "handoff.md")
        self.assertEqual(Path(report.repository["root"]).resolve(), self.repo.resolve())
        self.assertEqual(report.repository["head"], self.head)

    def test_included_config_blocks_status_without_reading_it(self) -> None:
        git(self.repo, "config", "include.path", "../outside.cfg")
        report = preflight.run_preflight(self.repo, "handoff.md")
        wt = [f for f in report.findings if f.subject == "working-tree"]
        self.assertEqual([f.status for f in wt], ["unknown"])
        self.assertIn("include", wt[0].message)


# --------------------------------------------------------------------------
# Finding 2: --output can overwrite arbitrary files
# --------------------------------------------------------------------------
class CliOutputSafety(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.repo = make_repo(self.tmp, {"a.txt": "a\n"}, branch="main")
        self.head = head_of(self.repo)
        write(self.repo, "handoff.md", f"Branch: main\nHEAD: {self.head}\n")
        exclude_from_status(self.repo, "handoff.md")

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def test_output_option_cannot_overwrite_handoff(self) -> None:
        handoff = self.repo / "handoff.md"
        original = handoff.read_bytes()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            cli.main(["--project-root", str(self.repo), "--handoff", "handoff.md",
                      "--output", "handoff.md"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(handoff.read_bytes(), original)

    def test_output_option_cannot_write_outside_root(self) -> None:
        target = self.tmp / "victim.txt"
        target.write_text("keep me\n", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["--project-root", str(self.repo), "--handoff", "handoff.md",
                      "--output", str(target)])
        self.assertEqual(target.read_text(encoding="utf-8"), "keep me\n")

    def test_cli_writes_nothing_to_disk(self) -> None:
        before = sorted(p.relative_to(self.repo).as_posix()
                        for p in self.repo.rglob("*") if ".git" not in p.parts)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["--project-root", str(self.repo), "--handoff", "handoff.md", "--format", "json"])
        after = sorted(p.relative_to(self.repo).as_posix()
                       for p in self.repo.rglob("*") if ".git" not in p.parts)
        self.assertEqual(before, after)
        json.loads(out.getvalue())


# --------------------------------------------------------------------------
# Finding 3: manifest typos and wrong types must not silently bypass checks
# --------------------------------------------------------------------------
class ManifestStrictness(unittest.TestCase):
    def _parse(self, data) -> None:
        parse_manifest_text(json.dumps(data))

    def test_misspelled_repository_field_rejected(self) -> None:
        with self.assertRaises(ManifestError) as ctx:
            self._parse({"schema_version": 1, "repository": {"expected_hed": "abcdef1"}})
        self.assertIn("expected_hed", str(ctx.exception))

    def test_misspelled_sha256_field_rejected(self) -> None:
        for key in ("sha-256", "sha_256", "sha256sum", "SHA256"):
            with self.subTest(key=key), self.assertRaises(ManifestError):
                self._parse({"schema_version": 1, "evidence": [{"path": "x.txt", key: "0" * 64}]})

    def test_misspelled_fields_in_approvals_and_claims_rejected(self) -> None:
        with self.assertRaises(ManifestError):
            self._parse({"schema_version": 1, "approvals": [{"id": "p", "statu": "granted"}]})
        with self.assertRaises(ManifestError):
            self._parse({"schema_version": 1, "claims": [{"id": "c", "txt": "t", "status": "agent_reported"}]})

    def test_schema_version_must_be_integer_one(self) -> None:
        for bad in (True, False, 1.0, "1", None):
            with self.subTest(value=bad), self.assertRaises(ManifestError):
                self._parse({"schema_version": bad})

    def test_field_types_enforced(self) -> None:
        bad_cases = [
            {"repository": {"expected_branch": 7}},
            {"repository": {"expected_head": 1234567}},
            {"evidence": [{"path": 5}]},
            {"evidence": [{"path": "x.txt", "label": 9}]},
            {"approvals": [{"id": 1, "status": "pending"}]},
            {"approvals": [{"id": "p", "status": "pending", "description": ["x"]}]},
            {"claims": [{"id": "c", "text": None, "status": "agent_reported"}]},
        ]
        for extra in bad_cases:
            with self.subTest(extra=extra), self.assertRaises(ManifestError):
                self._parse({"schema_version": 1, **extra})

    def test_typo_cannot_bypass_hash_check_end_to_end(self) -> None:
        tmp_ctx = temp_dir()
        tmp = Path(tmp_ctx.__enter__())
        try:
            repo = make_repo(tmp, {"reports/run.txt": "original\n"}, branch="main")
            head = head_of(repo)
            write(repo, "handoff.md", f"Branch: main\nHEAD: {head}\n")
            exclude_from_status(repo, "handoff.md", "manifest.json")
            write(repo, "reports/run.txt", "tampered\n")  # no longer matches the recorded hash
            write(repo, "manifest.json", json.dumps({
                "schema_version": 1,
                "evidence": [{"path": "reports/run.txt", "sha_256": "0" * 64}],  # typo: sha_256
            }))
            report = preflight.run_preflight(repo, "handoff.md", "manifest.json")
            self.assertTrue(report.errors, "misspelled evidence field was silently accepted")
            self.assertEqual(report.exit_code(), 2)
        finally:
            tmp_ctx.__exit__(None, None, None)


# --------------------------------------------------------------------------
# Finding 4: Markdown links resolve relative to the handoff document
# --------------------------------------------------------------------------
class NestedReferences(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.repo = make_repo(self.tmp, {
            "README.md": "root readme\n",
            "docs/notes/a.md": "note a\n",
            "docs/handoffs/h.md": "placeholder\n",
        }, branch="main")
        self.head = head_of(self.repo)

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def _handoff(self, body: str) -> None:
        write(self.repo, "docs/handoffs/h.md",
              f"Branch: main\nHEAD: {self.head}\n\n{body}\n")

    def _ref_findings(self, report) -> dict[str, str]:
        return {f.subject: f.status for f in report.findings if f.category == "reference"}

    def test_link_resolves_relative_to_handoff_directory(self) -> None:
        self._handoff("See [note](../notes/a.md).")
        report = preflight.run_preflight(self.repo, "docs/handoffs/h.md")
        self.assertEqual(self._ref_findings(report), {"../notes/a.md": "verified_metadata"})

    def test_link_with_parent_segments_to_root_file(self) -> None:
        self._handoff("See [readme](../../README.md).")
        report = preflight.run_preflight(self.repo, "docs/handoffs/h.md")
        self.assertEqual(self._ref_findings(report), {"../../README.md": "verified_metadata"})

    def test_missing_nested_link_is_stale(self) -> None:
        self._handoff("See [gone](../notes/missing.md).")
        report = preflight.run_preflight(self.repo, "docs/handoffs/h.md")
        self.assertEqual(self._ref_findings(report), {"../notes/missing.md": "stale"})

    def test_link_escaping_root_is_rejected(self) -> None:
        self._handoff("See [out](../../../outside.md).")
        report = preflight.run_preflight(self.repo, "docs/handoffs/h.md")
        self.assertEqual(self._ref_findings(report), {"../../../outside.md": "rejected"})

    def test_link_through_symlink_escape_is_rejected(self) -> None:
        if not can_symlink(self.tmp):
            self.skipTest("symlink creation not permitted on this platform/account")
        outside = self.tmp / "outside-dir"
        outside.mkdir()
        (outside / "secret.md").write_text("x\n", encoding="utf-8")
        os.symlink(outside, self.repo / "docs" / "handoffs" / "linked", target_is_directory=True)
        self._handoff("See [s](linked/secret.md).")
        report = preflight.run_preflight(self.repo, "docs/handoffs/h.md")
        self.assertEqual(self._ref_findings(report), {"linked/secret.md": "rejected"})

    def test_evidence_paths_remain_repository_root_relative(self) -> None:
        self._handoff("## Evidence\n\n- `docs/notes/a.md`\n- `../README.md`\n")
        report = preflight.run_preflight(self.repo, "docs/handoffs/h.md")
        self.assertEqual(self._ref_findings(report), {
            "docs/notes/a.md": "verified_metadata",
            "../README.md": "rejected",
        })

    def test_handoff_path_given_absolute_inside_root(self) -> None:
        self._handoff("See [note](../notes/a.md).")
        absolute = self.repo / "docs" / "handoffs" / "h.md"
        report = preflight.run_preflight(self.repo, absolute)
        self.assertEqual(report.errors, [])
        self.assertEqual(self._ref_findings(report), {"../notes/a.md": "verified_metadata"})


# --------------------------------------------------------------------------
# Finding 5: "no contradiction" must not be reported as verified readiness
# --------------------------------------------------------------------------
class ReadinessSemantics(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.repo = make_repo(self.tmp, {"docs/a.md": "a\n"}, branch="main")
        self.head = head_of(self.repo)

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def _handoff(self, extra: str = "") -> None:
        write(self.repo, "handoff.md", f"Branch: main\nHEAD: {self.head}\n{extra}")
        exclude_from_status(self.repo, "handoff.md", "manifest.json")

    def _manifest(self, data: dict) -> None:
        write(self.repo, "manifest.json", json.dumps({"schema_version": 1, **data}))

    def _readiness(self, report) -> dict:
        return to_dict(report)["readiness"]

    def test_clean_state_is_no_contradiction_not_verified_readiness(self) -> None:
        self._handoff()
        report = preflight.run_preflight(self.repo, "handoff.md")
        r = self._readiness(report)
        self.assertEqual(r["outcome"], "no_contradiction_detected")
        self.assertIs(r["verified_readiness"], False)
        self.assertIs(r["authorizes_actions"], False)
        self.assertEqual(report.exit_code(), 0)

    def test_pending_approval_requires_review(self) -> None:
        self._handoff("\nPending approval: publish the summary.\n")
        report = preflight.run_preflight(self.repo, "handoff.md")
        self.assertEqual(self._readiness(report)["outcome"], "review_required")
        self.assertEqual(report.exit_code(), 3)

    def test_granted_approval_never_authorises(self) -> None:
        self._handoff()
        self._manifest({"approvals": [{"id": "publication", "status": "granted", "description": "x"}]})
        report = preflight.run_preflight(self.repo, "handoff.md", "manifest.json")
        r = self._readiness(report)
        self.assertNotEqual(r["outcome"], "no_contradiction_detected")
        self.assertIs(r["authorizes_actions"], False)

    def test_missing_evidence_is_contradiction_not_clean(self) -> None:
        self._handoff()
        self._manifest({"evidence": [{"path": "reports/none.json"}]})
        report = preflight.run_preflight(self.repo, "handoff.md", "manifest.json")
        self.assertEqual(self._readiness(report)["outcome"], "contradiction_found")
        self.assertEqual(report.exit_code(), 1)

    def test_not_a_repository_is_review_required_not_clean(self) -> None:
        plain = self.tmp / "plain"
        plain.mkdir()
        (plain / "handoff.md").write_text("Branch: main\nHEAD: abc1234\n", encoding="utf-8")
        saved = os.environ.get("GIT_CEILING_DIRECTORIES")
        os.environ["GIT_CEILING_DIRECTORIES"] = str(self.tmp)
        try:
            report = preflight.run_preflight(plain, "handoff.md")
        finally:
            if saved is None:
                os.environ.pop("GIT_CEILING_DIRECTORIES", None)
            else:
                os.environ["GIT_CEILING_DIRECTORIES"] = saved
        self.assertEqual(self._readiness(report)["outcome"], "review_required")
        self.assertEqual(report.exit_code(), 3)

    def test_markdown_states_it_is_not_verified_readiness(self) -> None:
        from siftelo.report import to_markdown
        self._handoff()
        text = to_markdown(preflight.run_preflight(self.repo, "handoff.md"))
        self.assertIn("not verified readiness", text.lower())
        self.assertIn("## Readiness", text)


# --------------------------------------------------------------------------
# Windows-specific containment checks
# --------------------------------------------------------------------------
class WindowsPathSafety(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.root = self.tmp / "root"
        self.root.mkdir()
        write(self.root, "docs/a.md", "a\n")

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def test_reserved_device_names_rejected(self) -> None:
        for bad in ("NUL", "docs/CON.txt", "aux.md", "docs/com1", "lpt9.log", "nul.tar.gz"):
            with self.subTest(path=bad), self.assertRaises(PathSafetyError):
                resolve_within(self.root, bad)

    def test_alternate_data_streams_and_colons_rejected(self) -> None:
        for bad in ("docs/a.md:secret", "docs:a.md", "docs/a.md::$DATA"):
            with self.subTest(path=bad), self.assertRaises(PathSafetyError):
                resolve_within(self.root, bad)

    def test_trailing_dot_or_space_components_rejected(self) -> None:
        for bad in ("docs/a.md.", "docs/a.md ", "docs./a.md"):
            with self.subTest(path=bad), self.assertRaises(PathSafetyError):
                resolve_within(self.root, bad)

    def test_ordinary_nested_path_still_accepted(self) -> None:
        self.assertEqual(resolve_within(self.root, "docs/a.md"), (self.root / "docs" / "a.md").resolve())

    @unittest.skipUnless(sys.platform == "win32", "directory junctions are Windows-specific")
    def test_directory_junction_escape_rejected(self) -> None:
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "secret.md").write_text("x\n", encoding="utf-8")
        junction = self.root / "jct"
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                              capture_output=True, text=True, shell=False)
        if proc.returncode != 0:
            self.skipTest(f"junction creation unavailable: {proc.stdout.strip()} {proc.stderr.strip()}")
        with self.assertRaises(PathSafetyError):
            resolve_within(self.root, "jct/secret.md")


if __name__ == "__main__":
    unittest.main()
