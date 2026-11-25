# Siftelo: continuous-integration plan (active, manual trigger only)

Status: the workflow is in `.github/workflows/ci-manual-validation.yml` and has run once on GitHub-hosted runners
(run 45613575986, all six jobs passed). It runs only when a
person starts it from the Actions tab. It never runs on a push or a pull request. Nothing here publishes, uploads
or tags anything.

## Files

- `.github/workflows/ci-manual-validation.yml`: the workflow. Manual trigger only, six jobs, read-only, no artifacts
  and no cache.
- `beta/proposed-ci/ci_check.py`: the driver that does every check. It is portable (Windows and Linux) and runs
  without a shell. It was run locally on Windows 11 (TRC-014, TRC-014A, TRC-016B, TRC-017). Linux results come from
  an independent review of the TRC-014 candidate, not from this workspace. The hosted result is run 45613575986
  (listed in `README.md`, "Tested and untested").

## Goal

Show that the source passes its tests, that the wheel reproduces and the source distribution works, that the
installed command runs, and that the demonstrations exit with the expected codes. CI does not certify readiness
and does not replace human review.

## Matrix

| Axis | Values | Why |
|---|---|---|
| OS | `windows-latest`, `ubuntu-latest` | Windows 11 (3.13.3) and Linux (3.13.5, independent review) have run the suite. The hosted run (TRC-017) passed on Windows and Ubuntu runners. |
| Python | 3.11, 3.12, 3.13 | `requires-python >=3.11`. All three passed on GitHub-hosted runners (TRC-017). Only 3.13 has been run on a local machine. |
| Git | the runner's default Git | The tool needs Git 2.32 or newer by design. The floor is untested. |

Six jobs in total. At most three run at once, and each job has a 20-minute timeout.

## Trigger, permissions and cost

- Trigger: `workflow_dispatch` only. There is no push or pull-request trigger, so nothing runs without a person
  starting it.
- Permissions: `contents: read`. No secrets. No deployment or publication credentials.
- No artifact upload and no cache. Results are read from the job logs.
- Cost: GitHub Free, no payment method on file (checked on 2026-11-25). Included compute covers about 31 runs of
  the expected cost and about 12 runs of the worst case. Without a payment method, Actions stops once the included
  compute is used up; it is not billed. See `beta/LIMITATIONS.md`, L-21.

## What the driver checks, in order

Every command below must give the expected exit code. Any other code fails the job, with the last lines of its
output.

1. Record the Python version and `git --version`.
2. Run the unit tests in the repository: `python -m unittest discover -s tests`, expected 0. The job log shows the
   `Ran N tests` line.
3. Build the wheel and the source distribution twice, each from a clean copy of the distribution inputs, with
   `SOURCE_DATE_EPOCH` set to the commit time. The two wheel hashes must match. The sdist hash is reported only.
4. Check the wheel's contents: only the `siftelo` package and its metadata; the licence file present; the
   metadata carries `License-Expression: Apache-2.0`.
5. Extract the sdist into a new folder and run the unit tests there, expected 0. The job log shows the `Ran N tests`
   line for this run too.
6. Rebuild the wheel from the extracted sdist. Its hash must match the clean-copy wheel.
7. Create a fresh virtual environment and install the wheel with `--no-index --no-deps`. Run `siftelo --version`
   (expected `siftelo 0.1.0`) and `siftelo --help`, both expected 0.
8. Build the two demonstrations from the extracted sdist's `examples/`: the correct build and the `--stale` build.
   Run `siftelo` on each example, in Markdown and JSON. Expected: correct build 3, stale build 1.
9. Write the wheel, the sdist, `SHA256SUMS.txt` and the demonstration reports to the artifacts folder. The workflow
   prints `SHA256SUMS.txt` into the job log.

Each job also logs the runner image, the platform, the Python executable, the pip and Git versions, and the
installed setuptools version.

## Actions, pinned and reviewed as far as possible

Each action is pinned to a full commit SHA, with the release tag as a comment.

| Action | Pinned tag | Runtime | Pinned commit |
|---|---|---|---|
| `actions/checkout` | v7.0.1 | node24 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-python` | v7.1.0 | node24 | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` |

Earlier pins (checkout v4.4.0, setup-python v5.6.0, and upload-artifact v4.6.2) used the deprecated node20
runtime and were replaced. `upload-artifact` is no longer used, because the workflow uploads nothing.

Scope of the review (TRC-016B): the bundled entry points (`dist/index.js` for checkout; `dist/setup/index.js` and
`dist/cache-save/index.js` for setup-python) and their `@actions/*` dependencies were inspected statically. The
bundles were not rebuilt from source and were not executed. The cache post-step does nothing unless a `cache`
input is set, and the workflow sets none. No advisory was found for these tags in the GitHub advisory data or
OSV. A pinned commit only fixes which code runs; it is not a safety verdict. The owner must still review the
action code at these commits before activation.

## Build backend

- The workflow installs `setuptools==84.2.1` with `--only-binary=:all: --require-hashes --no-deps`, from the
  official package index (PyPI). The wheel checksum is listed in the workflow file.
- The minimum in `pyproject.toml` is `setuptools>=84.1.0`. That excludes the affected releases: GHSA-h35f-9h28-mq5c
  / CVE-2026-59890 (fixed in 83.0.0; the earlier 80.9.0 pin falls in this range) and GHSA-xmj3-9gf7-h52w (affected
  from 38.2.2 up to 84.1.0).
- The earlier release candidate (TRC-014A and TRC-015A) was built with setuptools 80.9.0. The current release
  build uses 84.2.1, so the release baseline was re-established in TRC-016B; the new checksums are in the
  TRC-016B report, not in this file.
- The driver calls the setuptools backend directly. No separate `build` frontend is installed.

## Network use

- The GitHub actions use the network: `actions/checkout` fetches the repository, and `actions/setup-python`
  provisions Python on the runner.
- The `pip install` of the pinned setuptools downloads from PyPI, and is verified by hash.
- The build and the offline wheel install (`--no-index`) use no network.

## What the plan does not do

- It does not publish to any package index, create a release, post a comment, or tag a version.
- It does not run any tool on a handoff from outside the repository.
- It does not use secrets, caches or artifact uploads.

## Open items

- The owner must still review the pinned action code (see above) before the next hosted run. Setuptools 84.2.1 is
  approved in TRC-016B.
- The first hosted run (run 45613575986) passed all six jobs. The Linux result from the independent review is not
  a hosted run.
- GitHub parsed and ran the workflow in TRC-017. No local YAML parser has been run on it.
- Generated setuptools metadata (`PKG-INFO`, `setup.cfg`, `*.egg-info`) stays in the sdist on purpose. It is normal
  setuptools output (TRC-013).
