# Siftelo

> **Clarity before action.**

Siftelo is a small, **read-only** command-line preflight. It answers one question:

> Does this Markdown handoff still match the real Git repository?

It reads the handoff, an optional JSON manifest and the repository. It reports each factual
reference with a conservative status and an overall outcome. It is designed not to run project tests,
not to write to the repository or to any other file, and not to run commands or programs supplied by the
repository; it runs only a fixed set of read-only Git commands (see `beta/SECURITY-GUIDANCE.md`). The test suite
checks these behaviours for the cases it covers. It uses only the Python standard library.

**New here?** Start with [`beta/START-HERE-SIFTELO.md`](beta/START-HERE-SIFTELO.md): install, a synthetic
demonstration and the expected results, for Windows and Linux.

**Status: 0.1.0 early public beta.** Distributed as a wheel and a source distribution with the GitHub
release. Not on PyPI. Tested on Windows 11 (Python 3.13.3, Git 2.52.0), on GitHub-hosted Windows and Linux
runners with Python 3.11, 3.12 and 3.13, and on Linux by an independent review. See "Tested and
untested" below.

**Not a sandbox.** Siftelo reduces specific risks it has tested. It does not make an untrusted
repository safe to open, and a result is not a security decision or an approval.

## Install

From the GitHub release (recommended). Check both the wheel and the source distribution against `SHA256SUMS.txt`
first, then install the wheel into a new virtual environment with no network access.

Windows (PowerShell):

```powershell
Get-FileHash -Algorithm SHA256 .\siftelo-0.1.0-py3-none-any.whl, .\siftelo-0.1.0.tar.gz
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --no-deps .\siftelo-0.1.0-py3-none-any.whl
.\.venv\Scripts\siftelo.exe --version
```

Linux (bash):

```bash
sha256sum siftelo-0.1.0-py3-none-any.whl siftelo-0.1.0.tar.gz
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps ./siftelo-0.1.0-py3-none-any.whl
.venv/bin/siftelo --version
```

Expected output of the version command: `siftelo 0.1.0`. The full walk-through is `beta/START-HERE-SIFTELO.md`;
the full install guide, including the source-tree route and troubleshooting, is `beta/INSTALLATION.md`.

## Run

```powershell
siftelo --project-root <repo> --handoff <handoff.md> [--manifest <manifest.json>] [--format json|markdown]
```

- `--project-root`: the approved root. Project content (handoff, links, evidence, manifest) is read
  only inside it. The root must hold its own `.git` directory or pointer file; Siftelo does not
  search upward.
- `--handoff` and `--manifest`: relative to the project root, or absolute and inside it.
- `--format`: `markdown` (default) or `json`, written to stdout. There is no output-file option;
  redirect stdout if you want a copy.
- `--allow-external-git-metadata`: approves Git metadata outside the root (linked worktrees,
  `--separate-git-dir`). Off by default. Approve only metadata you control.

### Exit codes

| code | outcome | meaning |
|---|---|---|
| 0 | `no_contradiction_detected` | the checks found no contradiction. **This is not verified readiness** and authorises nothing. |
| 1 | `contradiction_found` | at least one `stale` or `rejected` item |
| 2 | `error` | the handoff or manifest could not be processed, or the usage was wrong |
| 3 | `review_required` | nothing contradicted, but items are unknown, unverified, pending or blocked |

Both output formats carry a `readiness` object with `verified_readiness: false` and
`authorizes_actions: false`. Siftelo does not certify readiness and does not authorise an action.

## Statuses

| status | meaning |
|---|---|
| `verified_metadata` | checked against Git metadata, file existence, or a SHA-256 match |
| `stale` | a recorded fact contradicts the repository now (includes missing files) |
| `rejected` | a reference points outside the root (symlink, junction, `..`, absolute, device name, colon); not followed |
| `unknown` | cannot be established safely here (detached HEAD, dirty tree, blocked Git metadata, ...) |
| `agent_reported` | the handoff author's claim, a test-success statement, or a manifest-recorded approval. **Not verified.** |

## Demonstration

The demonstration takes about five minutes and uses two made-up repositories. The builder is in the source
distribution (`examples/`), not in the wheel, so extract `siftelo-0.1.0.tar.gz` first. The complete commands for
Windows and Linux, with the expected exit code for each run, are in `beta/START-HERE-SIFTELO.md` (sections 4 and 5).

In short (Windows, PowerShell, in the folder that holds the downloaded files and the virtual environment):

```powershell
mkdir src
tar -xzf .\siftelo-0.1.0.tar.gz -C .\src
python .\src\siftelo-0.1.0\examples\build_demo.py .\demo
python .\src\siftelo-0.1.0\examples\build_demo.py .\demo-stale --stale
.\.venv\Scripts\siftelo.exe --project-root .\demo\interrupted-work --handoff handoff.md --manifest manifest.json
.\.venv\Scripts\siftelo.exe --project-root .\demo-stale\interrupted-work --handoff handoff.md --manifest manifest.json
```

The correct build exits **3** (a person should review the listed items). The stale build exits **1** (a recorded
fact no longer matches the repository). `beta/QUICKSTART.md` explains each step.

## Name and compatibility

Siftelo was called TraceCue during development (milestones TRC-004 to TRC-013; earlier milestones
used the name agent-project-navigator). The rename is listed below. No verification logic, exit code, readiness rule or approval rule changed.

| before (TRC-004 to TRC-013, as TraceCue) | now (Siftelo 0.1.0) |
|---|---|
| `python -m tracecue` | `python -m siftelo` |
| console command `tracecue` | `siftelo` (no alias kept) |
| import path `tracecue` | `siftelo` |
| distribution name `tracecue` | `siftelo` |
| JSON `schema` `tracecue/preflight-report` | `siftelo/preflight-report` (same `schema_version` 2) |
| Markdown title `# TraceCue Handoff Preflight` | `# Siftelo Handoff Preflight` |

Consumers that match the JSON `schema` string or the module, command or distribution name must
update them. Earlier names (`agent-project-navigator`, `apn-*`) are historical; the milestone
identifiers in reports and test comments are kept as references.

## Tested and untested

| item | status |
|---|---|
| Python | 3.11, 3.12 and 3.13: **tested on GitHub-hosted runners** (Windows and Ubuntu; all six jobs passed). 3.13.3 (Windows 11) and 3.13.5 (Linux, independent review) locally. |
| Git | 2.52.0 (Windows 11) and 2.47.3 (Linux): **tested**. Hosted runners used Git 2.56.1. The 2.32 minimum is a design target, **untested**. |
| Operating systems | Windows 11 locally and Windows on GitHub-hosted runners: **tested**. Linux: **tested** on Ubuntu runners and by independent review. macOS: **not run**. |

Test results by platform:

- Windows 11, Python 3.13.3, Git 2.52.0: 227 tests, all passed.
- Linux, Python 3.13.5, Git 2.47.3 (independent review, TRC-014A): 226 passed, 1 skipped (a
  Windows-specific test), 0 failures.
- GitHub-hosted runs (manual run 45613575986 on commit `a83d15d`, TRC-017): Ubuntu and Windows, Python 3.11, 3.12
  and 3.13. Each of the six jobs ran 227 tests and passed, and each ran the offline install and the eight CLI
  demonstration checks.

Both runs covered the extracted-sdist tests, the offline installation, the CI driver and the eight
CLI demonstration checks (two synthetic examples, correct and stale builds, Markdown and JSON).

## Privacy and security

- The source contains no network code, and Siftelo does not write files. Its report can contain absolute local paths,
  the branch name, changed file names (up to 200) and quoted handoff lines. Read `beta/PRIVACY.md`
  before you share a report.
- Read `beta/SECURITY-GUIDANCE.md` before you point Siftelo at a repository you do not control.
- Vulnerability reporting: see `SECURITY.md`. Do not open a public issue for a security problem.
- Feedback and bug reports: GitHub Issues, as described in `CONTRIBUTING.md`. Use synthetic examples only.

## Limitations

The most important limits (full list in `beta/LIMITATIONS.md`):

- Only exact `Blocked:` / `Blocker:` markers are read as blockers. Free-form wording is not inferred.
- Fenced and indented code blocks are skipped. Link checks confirm existence only.
- Repositories with per-worktree config, filters (for example Git LFS), includes or alternates get
  no working-tree status. This is deliberate and can look noisy.
- Submodules are not inspected. Reports are heuristic and may miss unusual phrasing.

## Tests

Standard `unittest`, using temporary synthetic Git repositories:

```powershell
python -m unittest discover -s tests
```

The suite contains 227 tests. On Linux one of them is skipped, because it is Windows-specific (see
"Tested and untested").

## Licence and copyright

Licensed under the Apache License, Version 2.0. See `LICENSE`.
Copyright 2026 Marsh. The notice is in `NOTICE`, which ships in the wheel and the source
distribution alongside `LICENSE`. The owner has given a good-faith confirmation of rights and provenance (not an absolute warranty); see `beta/LICENSING.md`.

## Scope

A local proof of value for a beta. It does not include an MCP adapter, a database, a dashboard,
cloud sync, test execution, or readiness certification. It is not published on PyPI.
