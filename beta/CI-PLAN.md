# Siftelo: continuous-integration plan (proposal, not active)

Status: a plan and a proposed workflow only. Nothing is active. The owner has created an empty private
repository, but no hosted workflow has run, and no workflow file is in `.github/`. Nothing here publishes,
uploads or tags anything.

## Files

- `proposed-ci/github-actions-ci.yml`: the proposed workflow. It sits outside `.github/` and cannot run.
- `proposed-ci/ci_check.py`: the driver that does every check. It is portable (Windows and Linux) and runs
  without a shell. It was run locally on Windows 11 (TRC-014 and TRC-014A). Linux results come from an independent
  review of the TRC-014 candidate, not from this workspace. It has not run on a hosted runner.

## Goal

Show, on every change, that the source passes its tests, that the wheel reproduces and the source distribution
works, that the installed command runs, and that the demonstrations exit with the expected codes. CI does not
certify readiness and does not replace human review.

## Matrix

| Axis | Values | Why |
|---|---|---|
| OS | `windows-latest`, `ubuntu-latest` | Windows 11 (3.13.3) and Linux (3.13.5, independent review) have run the suite. A hosted run has not. |
| Python | 3.11, 3.12, 3.13 | `requires-python >=3.11`. Only 3.13.3 and 3.13.5 have run. 3.11 and 3.12 are untested. |
| Git | the runner's default Git | The tool needs Git 2.32 or newer by design. The floor is untested. |

## What the driver checks, in order

Every command below must give the expected exit code. Any other code fails the job, with the last lines of its
output.

1. Record the Python version and `git --version`.
2. Run the unit tests in the repository: `python -m unittest discover -s tests`, expected 0.
3. Build the wheel and the source distribution twice, each from a clean copy of the distribution inputs, with
   `SOURCE_DATE_EPOCH` set to the commit time. The two wheel hashes must match. The sdist hash is reported only.
4. Check the wheel's contents: only the `siftelo` package and its metadata; the licence file present; the
   metadata carries `License-Expression: Apache-2.0`.
5. Extract the sdist into a new folder and run the unit tests there, expected 0.
6. Rebuild the wheel from the extracted sdist. Its hash must match the clean-copy wheel.
7. Create a fresh virtual environment and install the wheel with `--no-index --no-deps`. Run `siftelo --version`
   (expected `siftelo 0.1.0`) and `siftelo --help`, both expected 0.
8. Build the two demonstrations from the extracted sdist's `examples/`: the correct build and the `--stale` build.
   Run `siftelo` on each example, in Markdown and JSON. Expected: correct build 3, stale build 1.
9. Write the wheel, the sdist, `SHA256SUMS.txt` and the demonstration reports to the artifacts folder.

## Steps the owner must approve before activation

- **Action pins.** The workflow pins each action to a full commit SHA, with the release tag as a comment:
  `actions/checkout` v4.4.0, `actions/setup-python` v5.6.0, `actions/upload-artifact` v4.6.2. The SHAs were read
  from GitHub's public API on 2026-11-25. The owner must still review the action code before activation.
- **The build backend.** The workflow installs `setuptools==80.9.0` from the package index at run time. This is
  one of several network steps, not the only one. The checkout, setup-python (which provisions Python on the runner)
  and artifact-upload actions also use the network. The build and the offline wheel install use no network.
  The release candidate was built with that exact version. Without the install, the runner's
  own setuptools would be used, which is not pinned. Approve or replace this step.
- **No `build` frontend.** The earlier plan installed the `build` package unpinned. TRC-014 removed it: the driver
  calls the setuptools backend directly, as TRC-013 did, so no unpinned frontend is installed.

## What the plan does not do

- It does not publish to any package index, create a release, post a comment, or tag a version.
- It does not run any tool on a handoff from outside the repository.
- It runs pip only to install the pinned setuptools above. The network use of the GitHub Actions it names is not
  Siftelo's own.
- It gives the workflow read-only repository access (`permissions: contents: read`).
- It does not use secrets.

## Open items before the plan can run

- The repository exists (created by the owner: private, empty). Activation still needs the owner's approval.
- The owner must review the pinned action code and approve the setuptools install (see above).
- A hosted run on both operating systems is still needed before the matrix is trusted. The Linux result from the
  independent review does not replace it.
- The workflow has not been parsed by a YAML tool. No YAML parser is installed, and installing one was not approved.
- Generated setuptools metadata (`PKG-INFO`, `setup.cfg`, `*.egg-info`) stays in the sdist on purpose. It is normal
  setuptools output (TRC-013).
