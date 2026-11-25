"""Unit tests for path safety, manifest validation and handoff parsing."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from helpers import temp_dir, write

from siftelo.handoff import parse_handoff
from siftelo.manifest import ManifestError, parse_manifest_text
from siftelo.paths import PathSafetyError, resolve_within


class PathSafetyUnits(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temp_dir()
        self.tmp = Path(self._tmp.__enter__())
        self.root = self.tmp / "root"
        self.root.mkdir()
        write(self.root, "a/b.txt", "x")

    def tearDown(self) -> None:
        self._tmp.__exit__(None, None, None)

    def test_inside_path_resolves(self) -> None:
        self.assertEqual(resolve_within(self.root, "a/b.txt"), (self.root / "a" / "b.txt").resolve())

    def test_rejects_bad_inputs(self) -> None:
        for bad in ["", "   ", "../x", "a/../../x", "..\\x", "/etc/passwd", "\\\\server\\share", "C:/x", "a\x00b"]:
            with self.subTest(path=bad), self.assertRaises(PathSafetyError):
                resolve_within(self.root, bad)


class ManifestUnits(unittest.TestCase):
    def test_valid_minimal_manifest(self) -> None:
        m = parse_manifest_text(json.dumps({"schema_version": 1}))
        self.assertIsNone(m.expected_head)
        self.assertEqual(m.evidence, [])

    def test_full_manifest_normalises_hashes_and_head(self) -> None:
        m = parse_manifest_text(json.dumps({
            "schema_version": 1,
            "repository": {"expected_head": "ABCDEF1", "expected_branch": "main"},
            "evidence": [{"path": "x.txt", "sha256": "A" * 64}],
            "approvals": [{"id": "publication", "status": "granted"}],
            "claims": [{"id": "c", "text": "t", "status": "agent_reported"}],
        }))
        self.assertEqual(m.expected_head, "abcdef1")
        self.assertEqual(m.evidence[0].sha256, "a" * 64)
        self.assertEqual(m.approvals[0].status, "granted")

    def test_schema_violations(self) -> None:
        cases = [
            ([], "must be an object"),
            ({"schema_version": 2}, "schema_version must be the integer 1"),
            ({"schema_version": 1, "repository": {"expected_head": "zz"}}, "hex revision"),
            ({"schema_version": 1, "evidence": [{"path": "x", "sha256": "abc"}]}, "64 hex"),
            ({"schema_version": 1, "evidence": {}}, "must be an array"),
            ({"schema_version": 1, "approvals": [{"id": "p", "status": "maybe"}]}, "status must be one of"),
            ({"schema_version": 1, "claims": [{"id": "c", "text": "t", "status": "verified"}]}, "status must be one of"),
            ({"schema_version": 1, "evidence": [{"sha256": "0" * 64}]}, "path is required"),
        ]
        for data, fragment in cases:
            with self.subTest(data=data), self.assertRaises(ManifestError) as ctx:
                parse_manifest_text(json.dumps(data))
            self.assertIn(fragment, str(ctx.exception))

    def test_malformed_json_reports_position(self) -> None:
        with self.assertRaises(ManifestError) as ctx:
            parse_manifest_text('{\n  "schema_version": 1,\n  "evidence": [,]\n}')
        self.assertIn("line 3", str(ctx.exception))


class HandoffUnits(unittest.TestCase):
    def test_extracts_metadata_links_and_evidence(self) -> None:
        text = (
            "Branch: main\nHEAD: abcdef1234\n"
            "See [design](docs/design.md) and [site](https://example.com) and [top](#x).\n"
            "## Evidence\n- `reports/run.json`\n- `not a path`\n"
        )
        doc = parse_handoff(text, "h.md")
        self.assertEqual(doc.branch, "main")
        self.assertEqual(doc.head, "abcdef1234")
        targets = [(r.kind, r.target) for r in doc.references]
        self.assertIn(("link", "docs/design.md"), targets)
        self.assertIn(("evidence_path", "reports/run.json"), targets)
        self.assertNotIn(("evidence_path", "not a path"), targets)
        self.assertFalse(any("example.com" in t for _, t in targets))

    def test_invalid_revision_and_conflicts_warn(self) -> None:
        doc = parse_handoff("HEAD: not-a-sha!\nBranch: a\nBranch: b\n", "h.md")
        self.assertTrue(any("not a hex revision" in w for w in doc.warnings))
        self.assertTrue(any("conflicting branch" in w for w in doc.warnings))

    def test_test_claims_and_approvals_detected_not_verified(self) -> None:
        doc = parse_handoff("All tests pass.\nPending approval: publish it.\nNothing else.\n", "h.md")
        self.assertEqual([c.line for c in doc.test_claims], [1])
        self.assertEqual([p.line for p in doc.pending_approvals], [2])


if __name__ == "__main__":
    unittest.main()
