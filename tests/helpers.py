"""Shared test helpers. Creates only synthetic repositories inside temp directories."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

GIT_ID = ["-c", "user.name=Synthetic Test", "-c", "user.email=test@example.invalid",
          "-c", "commit.gpgsign=false"]


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *GIT_ID, *args], cwd=str(repo), capture_output=True, text=True,
                          check=True, shell=False)
    return proc.stdout.strip()


def write(repo: Path, rel: str, text: str) -> Path:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    return target


def make_repo(root: Path, files: dict[str, str] | None = None, branch: str = "main") -> Path:
    """Create a synthetic repo under `root` with one commit on `branch`."""
    repo = root / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", branch)
    for rel, text in (files or {"README.md": "synthetic\n"}).items():
        write(repo, rel, text)
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "synthetic base")
    return repo


def head_of(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def exclude_from_status(repo: Path, *names: str) -> None:
    """Keep test-authored handoff/manifest files out of `git status`, as a real workspace would."""
    with (repo / ".git" / "info" / "exclude").open("a", encoding="utf-8", newline="\n") as fh:
        for name in names:
            fh.write(name + "\n")


def temp_dir() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix="apn-test-")


def can_symlink(directory: Path) -> bool:
    probe = directory / "probe-target"
    link = directory / "probe-link"
    probe.write_text("x", encoding="utf-8")
    try:
        os.symlink(probe, link)
    except (OSError, NotImplementedError):
        return False
    finally:
        if link.is_symlink():
            link.unlink()
        probe.unlink()
    return True
