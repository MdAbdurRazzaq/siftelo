# Start here: Siftelo 0.1.0 early beta

Status: early public beta. Distributed as a wheel and a source distribution attached to the GitHub release.
Not on PyPI. Read this page first; the other documents in `beta/` and `README.md` hold the detail and are linked
below rather than repeated.

## 1. What Siftelo does

A handoff is a Markdown note that tells the next person or agent where the work stands: the commit, the branch,
the files, what was approved, what was tested. Between writing the note and reading it, the repository can move
on, and the note can quietly go out of date.

Siftelo reads the handoff, an optional JSON manifest and the Git repository, and reports whether the handoff still
matches the repository. Each factual reference gets a status. For example, `stale` means a recorded commit or file
hash no longer matches. Siftelo is designed to be read-only: it does not write files and does not use the network.

It does not decide whether the work is good, does not run project tests, and is not a sandbox. A clean result is
not approval and not readiness. See `SECURITY-GUIDANCE.md` and `LIMITATIONS.md` before you rely on a result.

## 2. When to use it

- Before you resume work from a handoff written earlier.
- Before you pass a handoff to another person or agent.
- In a script, to stop a pipeline when a handoff is out of date (exit codes, section 7).

Do not point it at a repository you do not control without reading `SECURITY-GUIDANCE.md` first.

## 3. Requirements

- Python 3.11, 3.12 or 3.13. Tested on Windows 11 with Python 3.13.3 and on GitHub-hosted Windows and Ubuntu runners
  with Python 3.11, 3.12 and 3.13.
- Git 2.32 or newer is the design target. Tested with Git 2.52.0 (Windows 11), 2.47.3 (Linux, independent review)
  and the hosted runners' Git. The 2.32 minimum itself has not been tested.
- No third-party Python packages. The wheel installs offline.

## 4. Install

Download the wheel, the source distribution and `SHA256SUMS.txt` from the same GitHub release. Check both
distribution files against `SHA256SUMS.txt` before you install. Each hash must match its line exactly.

### Windows (PowerShell)

Run these in the folder that holds the downloaded files:

```powershell
Get-FileHash -Algorithm SHA256 .\siftelo-0.1.0-py3-none-any.whl, .\siftelo-0.1.0.tar.gz
Get-Content .\SHA256SUMS.txt
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --no-deps .\siftelo-0.1.0-py3-none-any.whl
.\.venv\Scripts\siftelo.exe --version
```

Expected output of the last line: `siftelo 0.1.0`.

### Linux (bash)

```bash
sha256sum siftelo-0.1.0-py3-none-any.whl siftelo-0.1.0.tar.gz
grep -E 'siftelo-0.1.0(-py3-none-any\.whl|\.tar\.gz)$' SHA256SUMS.txt
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps ./siftelo-0.1.0-py3-none-any.whl
.venv/bin/siftelo --version
```

Expected output of the last line: `siftelo 0.1.0`.

Install into a new virtual environment, not into a system-wide Python. The full install guide, including the
source-tree route and troubleshooting, is `INSTALLATION.md`.

## 5. Five-minute synthetic demonstration

The demonstration builds two made-up Git repositories, each with a `handoff.md` and a `manifest.json`. It touches no
real project. The builder is in the source distribution, not in the wheel, so extract the source distribution first.
Continue in the same folder as section 4 and use the same virtual environment.

### Windows (PowerShell)

```powershell
mkdir src
tar -xzf .\siftelo-0.1.0.tar.gz -C .\src
python .\src\siftelo-0.1.0\examples\build_demo.py .\demo
python .\src\siftelo-0.1.0\examples\build_demo.py .\demo-stale --stale
.\.venv\Scripts\siftelo.exe --project-root .\demo\interrupted-work --handoff handoff.md --manifest manifest.json
.\.venv\Scripts\siftelo.exe --project-root .\demo\axe-core-synthetic --handoff handoff.md --manifest manifest.json
.\.venv\Scripts\siftelo.exe --project-root .\demo-stale\interrupted-work --handoff handoff.md --manifest manifest.json
.\.venv\Scripts\siftelo.exe --project-root .\demo-stale\axe-core-synthetic --handoff handoff.md --manifest manifest.json
```

### Linux (bash)

```bash
mkdir -p src
tar -xzf siftelo-0.1.0.tar.gz -C src
python3 src/siftelo-0.1.0/examples/build_demo.py ./demo
python3 src/siftelo-0.1.0/examples/build_demo.py ./demo-stale --stale
.venv/bin/siftelo --project-root ./demo/interrupted-work --handoff handoff.md --manifest manifest.json
.venv/bin/siftelo --project-root ./demo/axe-core-synthetic --handoff handoff.md --manifest manifest.json
.venv/bin/siftelo --project-root ./demo-stale/interrupted-work --handoff handoff.md --manifest manifest.json
.venv/bin/siftelo --project-root ./demo-stale/axe-core-synthetic --handoff handoff.md --manifest manifest.json
```

Expected exit codes, checked after each run (`$LASTEXITCODE` in PowerShell, `echo $?` in bash):

| run | exit code | meaning |
|---|---|---|
| `demo\interrupted-work` | **3** | a person should review the listed items |
| `demo\axe-core-synthetic` | **3** | a person should review the listed items |
| `demo-stale\interrupted-work` | **1** | a recorded fact no longer matches the repository |
| `demo-stale\axe-core-synthetic` | **1** | a recorded fact no longer matches the repository |

The builder refuses a folder that already exists. Choose new folder names if you run the demonstration again.
Exit 3 is not a pass, and exit 0 is not readiness. `QUICKSTART.md` explains each step and shows the Markdown and
JSON output.

## 6. Use it on a project you trust

1. Point `--project-root` at the folder that holds the repository's own `.git` directory (or pointer file).
   Siftelo does not search upward.
2. Give `--handoff` as a path relative to that root, or as an absolute path inside it. Add `--manifest` if you
   keep one.
3. Choose `--format markdown` (default) to read the report, or `--format json` for a script.
4. Keep `--allow-external-git-metadata` off unless the Git metadata is outside the root and you control it.
5. A dirty working tree gives `unknown` items, and a handoff kept as an uncommitted file inside the repository can
   produce review items. See "Dirty trees" in `LIMITATIONS.md`.

## 7. Read the result

| exit code | outcome | what to do |
|---|---|---|
| 0 | `no_contradiction_detected` | Nothing contradicts the handoff. This is not verified readiness and does not authorise anything. |
| 1 | `contradiction_found` | A `stale` or `rejected` item exists. Treat it as blocking until you have checked it. |
| 2 | `error` | The handoff or manifest could not be processed, or the command line was wrong. The report or stderr says why. |
| 3 | `review_required` | Nothing contradicts, but some items are `unknown`, unverified, pending or blocked. A person should look. |

| status | meaning |
|---|---|
| `verified_metadata` | Checked against Git metadata, a file's existence, or a SHA-256 match. |
| `stale` | A recorded fact contradicts the repository now, including a missing file. |
| `rejected` | A reference points outside the root (symlink, junction, `..`, absolute path, device name). It is not followed. |
| `unknown` | It cannot be established safely here (detached HEAD, dirty tree, blocked Git metadata). |
| `agent_reported` | A claim, a test-success statement or a manifest approval. It is **not verified**. |

Both output formats state `verified_readiness: false` and `authorizes_actions: false`.

## 8. Handle private information safely

- A report can contain absolute paths (including your Windows or Linux user name), branch names, changed file names
  (up to 200) and lines quoted from the handoff. Read `PRIVACY.md`, sections 4 and 5, before you share one.
- Redact a report before you paste it anywhere public or shared.
- Keep secrets, tokens, passwords, customer data and personal data out of handoffs and manifests.
- For feedback, use a synthetic repository (see `FEEDBACK.md`). Do not send private or client code.

## 9. Uninstall

Remove the package from its virtual environment, then delete the environment and the demonstration folders.
Siftelo does not create files of its own, so there is nothing else to remove.

```powershell
.\.venv\Scripts\python.exe -m pip uninstall siftelo
Remove-Item -Recurse -Force .\.venv, .\src, .\demo, .\demo-stale
```

Check the paths before you run the last command: it deletes everything inside the folders you name.

## 10. Report a problem or give feedback

- **Bugs, false positives, missed findings and general feedback:** open a GitHub issue on the repository. Use
  synthetic examples or redacted excerpts only. `FEEDBACK.md` lists the questions that help most and has a template.
- **Security problems:** do not open a public issue. Follow `SECURITY.md`.
- **Known limits:** read `LIMITATIONS.md` before you report a finding as a defect. Many reports are known limitations.

## 11. Where the detail lives

| need | document |
|---|---|
| Overview and command reference | `README.md` |
| Install options and troubleshooting | `INSTALLATION.md` |
| Walk-through with expected output | `QUICKSTART.md` |
| Sharing a report safely | `PRIVACY.md` |
| Using it on a repository you do not control | `SECURITY-GUIDANCE.md` |
| Known limits | `LIMITATIONS.md` |
| Feedback | `FEEDBACK.md` |
| Licence and notice | `LICENSE`, `NOTICE`, `LICENSING.md` |
