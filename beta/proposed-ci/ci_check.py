"""CI driver for Siftelo. Run by .github/workflows/ci-manual-validation.yml (manual trigger only).

It is run by that workflow, and can also be run locally. It is
written to behave the same on Windows and Linux:

- every external command is a list of arguments run without a shell;
- every path is built with pathlib and every Python call uses sys.executable;
- each Siftelo command and demo builder has an expected exit code, and any other code fails the job;
- nothing is downloaded: the wheel is installed with --no-index, and the build uses the setuptools that is
  already installed (the workflow installs a pinned version first; see beta/CI-PLAN.md).

Usage, from the repository root:

    python beta/proposed-ci/ci_check.py --artifacts <new-or-empty-directory>

The artifacts directory receives the wheel, the source distribution, SHA256SUMS.txt, and the demo reports.
Everything else is written to a temporary directory that is removed at the end.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

NAME = "siftelo"
VERSION = "0.1.0"
WHEEL_NAME = f"{NAME}-{VERSION}-py3-none-any.whl"
SDIST_NAME = f"{NAME}-{VERSION}.tar.gz"
TIMEOUT_SECONDS = 900

# Files the sdist includes (see MANIFEST.in). The clean copy used for the build must contain the same inputs.
INPUT_FILES = ["README.md", "LICENSE", "NOTICE", "SECURITY.md", "CONTRIBUTING.md", "pyproject.toml", "MANIFEST.in"]
INPUT_DIRS = ["src", "tests", "examples"]

BUILD_SNIPPET = (
    "import os, sys\n"
    "from setuptools import build_meta\n"
    "out = sys.argv[1]\n"
    "os.makedirs(out, exist_ok=True)\n"
    "print(build_meta.build_sdist(out))\n"
    "print(build_meta.build_wheel(out))\n"
)
WHEEL_ONLY_SNIPPET = (
    "import os, sys\n"
    "from setuptools import build_meta\n"
    "out = sys.argv[1]\n"
    "os.makedirs(out, exist_ok=True)\n"
    "print(build_meta.build_wheel(out))\n"
)


class CheckFailed(Exception):
    """A check did not produce the expected result."""


def log(message: str) -> None:
    print(message, flush=True)


def run(label: str, argv: list[str], *, expect: int = 0, cwd: Path | None = None,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run one command without a shell and require exactly the expected exit code."""
    full_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if env:
        full_env.update(env)
    proc = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                          env=full_env, timeout=TIMEOUT_SECONDS, shell=False)
    if proc.returncode != expect:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-30:])
        raise CheckFailed(f"{label}: expected exit {expect}, got {proc.returncode}\n{tail}")
    log(f"ok   {label}: exit {proc.returncode}")
    return proc


def run_tests(label: str, cwd: Path) -> None:
    """Run the unit tests and print how many ran. Any failure or error fails the job."""
    proc = run(label, [sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=cwd)
    summary = [line for line in proc.stderr.splitlines() if line.startswith("Ran ")]
    log(f"     {summary[-1] if summary else 'no summary line found'}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_inputs(repo: Path, dest: Path) -> None:
    """Copy only the distribution inputs into a clean directory (as a clean checkout would)."""
    dest.mkdir(parents=True)
    for name in INPUT_FILES:
        shutil.copyfile(repo / name, dest / name)
    for name in INPUT_DIRS:
        shutil.copytree(repo / name, dest / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (dest / "beta").mkdir()
    for md in sorted((repo / "beta").glob("*.md")):
        shutil.copyfile(md, dest / "beta" / md.name)


def build_in(tree: Path, out: Path, epoch: str, snippet: str) -> list[str]:
    run_out = run(f"build in {tree.name}", [sys.executable, "-c", snippet, str(out)], cwd=tree,
                  env={"SOURCE_DATE_EPOCH": epoch})
    return run_out.stdout.split()


def check_wheel_contents(wheel: Path) -> None:
    """The wheel holds only the package and its metadata, and carries the licence file."""
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        bad = [n for n in names if not (n.startswith(f"{NAME}/") or n.startswith(f"{NAME}-{VERSION}.dist-info/"))]
        if bad:
            raise CheckFailed(f"wheel has unexpected entries: {bad[:5]}")
        metadata = zf.read(f"{NAME}-{VERSION}.dist-info/METADATA").decode("utf-8")
    if "License-Expression: Apache-2.0" not in metadata:
        raise CheckFailed("wheel METADATA lacks 'License-Expression: Apache-2.0'")
    for notice in ("LICENSE", "NOTICE"):
        if f"{NAME}-{VERSION}.dist-info/licenses/{notice}" not in names:
            raise CheckFailed(f"wheel lacks licenses/{notice}")
    if "License-File: NOTICE" not in metadata:
        raise CheckFailed("wheel METADATA does not list NOTICE as a license file")
    log("ok   wheel contents: package and metadata only; LICENSE and NOTICE present")


def check_sdist_documents(sdist: Path) -> None:
    """The source distribution must carry the licence, the notice and the public project documents."""
    with tarfile.open(sdist, "r:gz") as tf:
        names = set(tf.getnames())
    for name in ("LICENSE", "NOTICE", "SECURITY.md", "CONTRIBUTING.md"):
        if f"{NAME}-{VERSION}/{name}" not in names:
            raise CheckFailed(f"sdist lacks {name}")
    log("ok   sdist contents: LICENSE, NOTICE, SECURITY.md and CONTRIBUTING.md present")


def extract_sdist(sdist: Path, dest: Path) -> Path:
    dest.mkdir(parents=True)
    with tarfile.open(sdist, "r:gz") as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest, filter="data")
        else:  # Python 3.11.0 to 3.11.3 have no extraction filters; the archive is ours and is checked above.
            tf.extractall(dest)
    roots = [p for p in dest.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise CheckFailed(f"sdist should extract to one folder, found {len(roots)}")
    return roots[0]


def venv_paths(venv_dir: Path) -> tuple[Path, Path]:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe", venv_dir / "Scripts" / f"{NAME}.exe"
    return venv_dir / "bin" / "python", venv_dir / "bin" / NAME


def check_demos(sdist_root: Path, work: Path, artifacts: Path, siftelo_cmd: Path) -> None:
    demo_builder = sdist_root / "examples" / "build_demo.py"
    ok_dir = work / "demo-ok"
    stale_dir = work / "demo-stale"
    run("demo builder, correct build", [sys.executable, str(demo_builder), str(ok_dir)], expect=0)
    run("demo builder, stale build", [sys.executable, str(demo_builder), str(stale_dir), "--stale"], expect=0)

    for example in ("interrupted-work", "axe-core-synthetic"):
        for variant, root, expect in (("correct", ok_dir, 3), ("stale", stale_dir, 1)):
            for fmt in ("markdown", "json"):
                example_dir = root / example
                proc = run(
                    f"siftelo {example} {variant} {fmt}",
                    [str(siftelo_cmd), "--project-root", str(example_dir), "--handoff", "handoff.md",
                     "--manifest", "manifest.json", "--format", fmt],
                    expect=expect,
                )
                ext = "md" if fmt == "markdown" else "json"
                (artifacts / f"demo-{example}-{variant}.{ext}").write_text(proc.stdout, encoding="utf-8",
                                                                             newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Siftelo CI driver.")
    parser.add_argument("--artifacts", required=True, type=Path,
                        help="new or empty directory that receives the distributions and reports")
    parser.add_argument("--source-date-epoch", default=None,
                        help="build time stamp (integer seconds). Default: the commit time from Git. "
                             "Needed only when the folder is not a Git checkout.")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    artifacts = args.artifacts.resolve()
    if artifacts.exists() and any(artifacts.iterdir()):
        raise SystemExit("FAIL: --artifacts must be a new or empty directory")
    artifacts.mkdir(parents=True, exist_ok=True)

    log(f"python: {sys.version.splitlines()[0]} ({sys.executable})")
    run("git version", ["git", "--version"])
    run_tests("unit tests, repository", repo)

    if args.source_date_epoch is not None:
        epoch = args.source_date_epoch
    else:
        try:
            epoch = run("commit time", ["git", "log", "-1", "--format=%ct"], cwd=repo).stdout.strip()
        except CheckFailed as exc:
            raise CheckFailed("the repository has no Git history here; pass --source-date-epoch "
                              f"to set the build time ({exc})") from exc
    if not epoch.isdigit():
        raise CheckFailed(f"could not read the build time: {epoch!r}")
    log(f"ok   build time (SOURCE_DATE_EPOCH): {epoch}")

    with tempfile.TemporaryDirectory(prefix="siftelo-ci-") as tmp_name:
        work = Path(tmp_name)

        # Two clean-copy builds: the wheel must reproduce, the sdist hash is reported only.
        copy_a = work / "copy-a"
        copy_b = work / "copy-b"
        copy_inputs(repo, copy_a)
        copy_inputs(repo, copy_b)
        build_a = work / "build-a"
        build_b = work / "build-b"
        names_a = build_in(copy_a, build_a, epoch, BUILD_SNIPPET)
        names_b = build_in(copy_b, build_b, epoch, BUILD_SNIPPET)
        wheel_a = build_a / WHEEL_NAME
        wheel_b = build_b / WHEEL_NAME
        sdist_a = build_a / SDIST_NAME
        if not (wheel_a.exists() and wheel_b.exists() and sdist_a.exists()):
            raise CheckFailed(f"unexpected build output: {names_a} / {names_b}")
        if sha256_of(wheel_a) != sha256_of(wheel_b):
            raise CheckFailed("wheel hash differs between two clean builds")
        log(f"ok   wheel reproduces across two clean builds: {sha256_of(wheel_a)}")
        check_wheel_contents(wheel_a)
        check_sdist_documents(sdist_a)

        # Extracted sdist: tests, then a wheel rebuilt from it, which must match.
        sdist_root = extract_sdist(sdist_a, work / "sdist")
        run_tests("unit tests, extracted sdist", sdist_root)
        rebuilt = work / "rebuilt"
        build_in(sdist_root, rebuilt, epoch, WHEEL_ONLY_SNIPPET)
        if sha256_of(rebuilt / WHEEL_NAME) != sha256_of(wheel_a):
            raise CheckFailed("wheel rebuilt from the extracted sdist differs from the clean-copy wheel")
        log("ok   wheel rebuilt from the extracted sdist matches")

        # Offline install into a fresh virtual environment.
        venv_dir = work / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(str(venv_dir))
        venv_py, siftelo_cmd = venv_paths(venv_dir)
        run("offline install of the wheel", [str(venv_py), "-m", "pip", "install", "--no-index", "--no-deps",
                                              str(wheel_a)])
        version = run("siftelo --version", [str(siftelo_cmd), "--version"]).stdout.strip()
        if version != f"{NAME} {VERSION}":
            raise CheckFailed(f"unexpected version output: {version!r}")
        run("siftelo --help", [str(siftelo_cmd), "--help"])

        # Demonstrations run from the extracted sdist, the same files a package user receives.
        check_demos(sdist_root, work, artifacts, siftelo_cmd)

        # Deliverables and checksums.
        shutil.copyfile(wheel_a, artifacts / WHEEL_NAME)
        shutil.copyfile(sdist_a, artifacts / SDIST_NAME)
        lines = [f"{sha256_of(artifacts / name)}  {name}" for name in (WHEEL_NAME, SDIST_NAME)]
        (artifacts / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        log("ok   checksums written: SHA256SUMS.txt")

    log("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed as exc:
        log(f"FAIL: {exc}")
        raise SystemExit(1)
