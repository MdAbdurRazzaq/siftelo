"""Build synthetic demo repositories for the preflight CLI.

Usage:
    python examples/build_demo.py <target-dir> [--stale]

Creates <target-dir>/<example>/ as a fresh synthetic Git repository for each
example, records the real HEAD and SHA-256 values into the handoff/manifest,
and excludes the handoff files from Git so the tree stays clean.

--stale  moves HEAD after recording and edits one evidence file, so the
         preflight reports stale HEAD and a SHA-256 mismatch.

The target directory must not already exist. Nothing outside it is written.
Only synthetic content is created; no real workspace is referenced or touched.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GIT_ID = ["-c", "user.name=Synthetic Demo", "-c", "user.email=demo@example.invalid"]


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *GIT_ID, *args], cwd=str(repo), capture_output=True, text=True,
                          check=True, shell=False)
    return proc.stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fill(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def _exclude(repo: Path, names: list[str]) -> None:
    exclude = repo / ".git" / "info" / "exclude"
    with exclude.open("a", encoding="utf-8", newline="\n") as fh:
        for name in names:
            fh.write(name + "\n")


INTERRUPTED_FILES = {
    "src/parser.py": "def parse(text):\n    return text.split()\n",
    "docs/notes/step2-fixtures.md": "Step 2 fixtures: regression inputs for tokenizer.\n",
    "docs/notes/perf-baseline.txt": "baseline: 12ms\n",
    "docs/notes/design.md": "AST shape: flat list of nodes.\n",
}

AXE_FILES = {
    "config/axe.config.json": '{"rules": {"color-contrast": {"enabled": true}}}\n',
    "fixtures/page.html": "<html><body><p>synthetic page</p></body></html>\n",
    "reports/axe-run.json": '{"violations": [{"id": "color-contrast", "nodes": 2}]}\n',
    "reports/summary.md": "Synthetic summary: 2 color-contrast violations.\n",
}


def build_example(target: Path, name: str, files: dict[str, str], branch: str,
                  handoff_src: Path, manifest_src: Path, evidence_for_hash: dict[str, str],
                  stale: bool) -> dict[str, Path]:
    """evidence_for_hash maps a template placeholder (e.g. SHA_REPORT) to a repo-relative path."""
    repo = target / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    for rel, text in files.items():
        _write(repo, rel, text)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "synthetic base")
    _git(repo, "checkout", "-q", "-b", branch)
    head = _git(repo, "rev-parse", "HEAD")
    values = {"HEAD": head, **{ph: _sha256(repo / rel) for ph, rel in evidence_for_hash.items()}}

    handoff_out = repo / "handoff.md"
    manifest_out = repo / "manifest.json"
    handoff_out.write_text(_fill(handoff_src.read_text(encoding="utf-8"), values), encoding="utf-8", newline="\n")
    manifest_out.write_text(_fill(manifest_src.read_text(encoding="utf-8"), values), encoding="utf-8", newline="\n")
    _exclude(repo, ["handoff.md", "manifest.json"])

    if stale:
        # HEAD moves after the handoff was recorded, and one evidence file changes.
        _write(repo, "src/parser.py", "def parse(text):\n    return text.strip().split()\n")
        _git(repo, "add", "src/parser.py")
        _git(repo, "commit", "-q", "-m", "work continued after handoff")
        for rel in evidence_for_hash.values():
            _write(repo, rel, (repo / rel).read_text(encoding="utf-8") + "edited after handoff\n")
            break

    return {"repo": repo, "handoff": handoff_out, "manifest": manifest_out}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    target = Path(argv[0]).resolve()
    stale = "--stale" in argv[1:]
    if target.exists():
        print(f"refusing to build: {target} already exists", file=sys.stderr)
        return 2
    target.mkdir(parents=True)

    built = {
        "interrupted-work": build_example(
            target, "interrupted-work", INTERRUPTED_FILES, "feature/parser-refactor",
            HERE / "interrupted-work" / "handoff.md", HERE / "interrupted-work" / "manifest.json",
            {"SHA_STEP2": "docs/notes/step2-fixtures.md"}, stale),
        "axe-core-synthetic": build_example(
            target, "axe-core-synthetic", AXE_FILES, "audit/synthetic-axe-run",
            HERE / "axe-core-synthetic" / "handoff.md", HERE / "axe-core-synthetic" / "manifest.json",
            {"SHA_REPORT": "reports/axe-run.json"}, stale),
    }
    for name, paths in built.items():
        print(f"{name}: repo={paths['repo']}")
        print(f"  handoff={paths['handoff']}")
        print(f"  manifest={paths['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
