# Siftelo

> **Clarity before action.**

Siftelo is a small, **read-only** command-line preflight. It answers one question:

> Does this Markdown handoff still match the real Git repository?

It reads the handoff, an optional JSON manifest and the repository. It reports each factual
reference with a conservative status and an overall outcome. It never runs project tests, never
writes to the repository or to any other file, and never executes programs supplied by the
repository. It uses only the Python standard library.

**Status: 0.1.0 beta candidate.** Not released. Tested on Windows 11 (Python 3.13.3, Git 2.52.0)
and on Linux (Python 3.13.5, Git 2.47.3, reported by an independent review). See "Tested and
untested" below.

**Not a sandbox.** Siftelo reduces specific risks it has tested. It does not make an untrusted
repository safe to open, and a result is not a security decision or an approval.

## Install

From a wheel built from this source (no network needed once `setuptools` is installed):

```powershell
python -m pip wheel . --no-deps --no-build-isolation -w dist
python -m venv .venv
.venv\Scripts\python.exe -m pip install --no-index --no-deps dist\siftelo-0.1.0-py3-none-any.whl
.venv\Scripts\siftelo.exe --version
```

The full guide, including the no-install route, is `beta/INSTALLATION.md` in the source tree.

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
`authorizes_actions: false`. Siftelo never certifies readiness and never authorises an action.

## Statuses

| status | meaning |
|---|---|
| `verified_metadata` | checked against Git metadata, file existence, or a SHA-256 match |
| `stale` | a recorded fact contradicts the repository now (includes missing files) |
| `rejected` | a reference points outside the root (symlink, junction, `..`, absolute, device name, colon); not followed |
| `unknown` | cannot be established safely here (detached HEAD, dirty tree, blocked Git metadata, ...) |
| `agent_reported` | the handoff author's claim, a test-success statement, or a manifest-recorded approval. **Not verified.** |

## Demonstration

The source tree ships a builder for two synthetic repositories (see `beta/QUICKSTART.md`):

```powershell
python examples\build_demo.py C:\siftelo-demo
```

The correct builds exit **3**. The `--stale` variant exits **1**.

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
| Python | 3.13.3 (Windows 11) and 3.13.5 (Linux): **tested**. Python 3.11 and 3.12: declared (`>=3.11`), **untested**. |
| Git | 2.52.0 (Windows 11) and 2.47.3 (Linux): **tested**. The 2.32 minimum is a design target, **untested**. Other versions untested. |
| Operating systems | Windows 11: **tested**. Linux: **tested** by independent review (see below). macOS: **not run**. |

Test results by platform:

- Windows 11, Python 3.13.3, Git 2.52.0: 227 tests, all passed.
- Linux, Python 3.13.5, Git 2.47.3 (independent review, TRC-014A): 226 passed, 1 skipped (a
  Windows-specific test), 0 failures.

Both runs covered the extracted-sdist tests, the offline installation, the CI driver and the eight
CLI demonstration checks (two synthetic examples, correct and stale builds, Markdown and JSON).

## Privacy and security

- Siftelo has no network access and writes nothing. Its report can contain absolute local paths,
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
cloud sync, test execution, or readiness certification. Package-registry and trademark checks are
pending.
