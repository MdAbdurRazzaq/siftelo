# Siftelo 0.1.0 beta candidate: installation

Status: beta candidate. Not released, not published on any package index.

## 1. Requirements

| requirement | tested | declared or designed for | not tested |
|---|---|---|---|
| Python | 3.13.3 (Windows 11); 3.13.5 (Linux, independent review) | `>=3.11` (declared) | 3.11 and 3.12 |
| Git | 2.52.0 (Windows 11); 2.47.3 (Linux, independent review) | 2.32 or newer (design target; the trust boundary relies on features from 2.32) | every other version, including the 2.32 floor |
| Operating system | Windows 11 and Linux (independent review) | Windows and Linux | macOS (not run) |
| Dependencies | none | standard library only | none |

Tested results are in the README ("Tested and untested"). The Linux results come from an independent review
of the TRC-014 candidate; they were not produced in this workspace.

Siftelo uses only the Python standard library. Nothing is downloaded at run time.

## 2. Run without installing (source tree)

From the root of a copy of the source tree, in PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m siftelo --version
python -m siftelo --project-root <path-to-repo> --handoff <handoff.md>
```

`--project-root` must contain its own `.git` directory or pointer file. Siftelo does not search upward.

## 3. Install from a wheel (offline)

Build the wheel from the source tree. The build below uses the `setuptools` already installed in the
interpreter, so it needs no network access. Check that it is 84.1.0 or newer, the minimum in `pyproject.toml`:
`python -c "import setuptools; print(setuptools.__version__)"`. The current release build uses `setuptools` 84.2.1.
Earlier candidates were built with 80.9.0, which has known advisories, and are superseded.

```powershell
python -m pip wheel . --no-deps --no-build-isolation -w dist
```

Install it into a new virtual environment, with no index:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --no-index --no-deps dist\siftelo-0.1.0-py3-none-any.whl
.venv\Scripts\siftelo.exe --version
```

Expected: `siftelo 0.1.0`, exit 0.

Building the wheel from the source tree writes `build/` and `src/siftelo.egg-info/` there. Build from a
copy if you need the tree left clean.

Avoid `pip install .` on a machine without network access: it runs the build in an isolated environment
and downloads the build backend.

## 4. Install from the source distribution

The source distribution contains the same package, the tests, the synthetic examples and the beta
documents. To use it, extract it into a new folder and build the wheel as in section 3. Do not
install from an unpacked source folder into a system-wide Python.

## 5. Check the files you received

Compare each file with `SHA256SUMS.txt`, which the release candidate provides next to the distributions:

```powershell
Get-FileHash -Algorithm SHA256 dist\siftelo-0.1.0-py3-none-any.whl
```

The hash must match the line for that file exactly.

## 6. Verify the installed command

```powershell
.venv\Scripts\siftelo.exe --help
.venv\Scripts\siftelo.exe --version
```

Then run the synthetic demonstration in `beta/QUICKSTART.md`. The demonstration exit codes (3, and 1 for the
stale build) are the expected results.

## 7. Uninstall

```powershell
.venv\Scripts\python.exe -m pip uninstall siftelo
```

Or delete the virtual environment folder.

## 8. Troubleshooting

| Exit 3, and the report says the project root has no `.git` of its own | The folder is not the root of a Git repository (Siftelo does not search upward). Point `--project-root` at the folder that holds `.git`. |
| Exit 2 | The handoff or manifest could not be processed (the report's `## Errors` section says why), or the command line was wrong (the usage message goes to stderr). |
| The report shows Git-related items as `unknown` | Git could not be run or its output was refused. Confirm that `git --version` works in the same terminal. |
| `pip` tries to reach the network | You used `pip install .` or `pip wheel` without `--no-build-isolation`. Use the commands in section 3. |
| Exit 3 on the demonstration builds | Expected: the handoffs list pending approvals and unverified claims. Exit 3 is not a failure. |
