# Contributing to Siftelo

Status: draft for the 0.1.0 beta. The owner enables GitHub Issues and pull requests before public release.

## Feedback and bug reports

Use **GitHub Issues** for non-sensitive feedback and bug reports. Use synthetic examples only; see
`beta/FEEDBACK.md`. Do not post a security problem in an issue; see [SECURITY.md](SECURITY.md).

## Substantial contributions: proposal first

For a new feature, a change in behaviour, or any change larger than a documentation fix or a single small bug fix,
open an issue that describes the proposal first. Wait for agreement on scope before you open a pull request.

## Pull requests

After agreement, or for a small fix, open a pull request. Before you open one:

- Use Python 3.11 or newer. Siftelo uses only the standard library; do not add a runtime dependency without agreement.
- Run the test suite from the repository root:

  ```
  python -m unittest discover -s tests
  ```

- Use synthetic examples only. Do not include private repositories, real handoffs, reports that contain paths or
  names, or secrets.
- Keep milestone references, test filenames and the rename history unchanged.

## Scope

Siftelo is deliberately read-only. Changes that add network access, write to the repository or to other files, run
commands taken from repository content, or add readiness or approval claims need agreement first.

## Licence of contributions

Unless you state otherwise, a contribution you submit for inclusion is licensed under the Apache License, Version 2.0,
as described in Section 5 of [LICENSE](LICENSE). See [NOTICE](NOTICE) for the copyright notice.
