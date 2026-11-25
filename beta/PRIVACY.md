# Siftelo 0.1.0 beta candidate: privacy statement

This statement describes what the Siftelo software does with data. It describes the code in this release
candidate, as tested on Windows 11 with Python 3.13.3 and Git 2.52.0. It is not a legal privacy notice for any
service, and no service operated by the project exists.

## 1. Summary

- Siftelo runs on your machine. It has **no network code**, **no telemetry**, and **no account**.
- It **writes nothing**. Its report goes to standard output. You decide whether to save, redirect or share it.
- It **reads** only the files you point it at: the handoff, the optional manifest, files named inside the
  project root, and the Git metadata of that repository (configuration, HEAD, branch, and working-tree status).
- The **report** can contain personal or sensitive information about your machine and your work. Read section 4
  before you share one.

## 2. What the software reads

| input | what is read | where it stays |
|---|---|---|
| `--handoff` file | its full text, to find revisions, branches, links, evidence paths, approvals, blockers and claims | in memory, for the run |
| `--manifest` file | its JSON, checked against the schema | in memory, for the run |
| files named by the handoff or manifest | existence, and SHA-256 when a hash is recorded | in memory, for the run |
| Git metadata in the repository | `config --local`, `HEAD`, branch name, and `status` (changed and untracked file names, capped at 200) | in memory, for the run |

Siftelo reads only inside `--project-root`, unless you pass `--allow-external-git-metadata`, which allows Git
metadata outside the root to be read. Use that option only for metadata you control.

## 3. What the software writes

- **Standard output:** the report, in Markdown (default) or JSON. Nothing else is printed by a successful run.
- **Standard error:** usage messages from the argument parser, if the command line is wrong.
- **Files:** none from a run. Siftelo creates no report, output, or temporary file, and it does not change the
  repository, the handoff or the manifest. Python may write its own bytecode cache (`__pycache__`) the first
  time the package is imported from a source tree; that is Python's behaviour, not a Siftelo output.
- **Network:** none.

Redirecting output with `>` is your own action; the software does not do it.

## 4. What the report contains

A report can include, in plain text:

- absolute local paths of the project root, the repository and the handoff (for example, a folder under your user
  profile), including the name of your user account when it is part of the path;
- the current branch name and the expected branch name;
- the commit hashes (HEAD) recorded and found;
- names of changed and untracked files, up to 200;
- lines quoted from your handoff, escaped for safe display in Markdown or a terminal, including any secret or
  customer data written in the handoff;
- the text of approvals, blockers and claims exactly as the handoff author wrote them.

JSON output carries the same content. Its strings are escaped, so exact bytes are preserved. Markdown output
escapes control characters and some Markdown syntax, but escapes are plain text: a literal `\x1b` in a handoff
looks the same as an escaped escape.

## 5. Before you share a report

1. Read the whole report. Assume every item in section 4 is present.
2. Remove absolute paths, user names, branch names, file names and quoted lines that you do not want to share.
3. Do not paste a report into a public issue, a public chat or a shared ticket without redacting it.
4. Do not put secrets in a handoff or manifest in the first place: tokens, passwords, private URLs, customer
   data and personal data.

A redaction option is not in this release (see LIMITATIONS, L-13).

## 6. Beta testers and feedback

- Feedback about the software does not need repository content. Describe the problem with a synthetic example,
  or with a redacted report. See `FEEDBACK.md`.
- The project does not yet have a feedback channel or a contact address. Nothing in this release sends your
  feedback anywhere. The owner decides how feedback is collected (see the release checklist).

## 7. Personal data in the project documents

The project documents and the package do not contain the owner's personal contact details, home address or
private identifiers. The copyright notice is `Copyright 2026 Marsh`, the owner's public developer alias (see `NOTICE`). The
development records in the repository's historical archives contain local paths from the owner's machine. They
are not part of the source distribution and the wheel, and should not be published as they are.

## 8. Changes

This statement applies to the 0.1.0 beta candidate. If the software starts to send data, store data or call
a network service, this statement must be revised before that release.
