# Siftelo 0.1.0 beta candidate: security guidance

## 1. Read this first

Siftelo is **not a sandbox**. It reads a repository's configuration and metadata, and it runs a small fixed set
of read-only Git commands. Its design reduces specific risks, listed in section 4. It does not make an arbitrary
untrusted repository safe to open.

Do not treat a Siftelo result as a security decision, as an approval, or as evidence that a repository is safe.

## 2. What Siftelo does to a repository

- Runs only these Git commands, with `shell=False`, a fixed argument list, a 10-second timeout, a 256 KiB output
  cap and a neutralised environment: `rev-parse` (four forms), `symbolic-ref`, `config --local --null --list`,
  and `status`. No write command exists in the code.
- Sets `GIT_CEILING_DIRECTORIES` to the parent of the project root, so Git does not search upward into an
  enclosing repository.
- Removes every `GIT_*` variable, and ignores the user's and the system's Git configuration files.
- Disables `core.fsmonitor` and `core.untrackedCache` on the command line.
- Refuses to run `status` if the local configuration defines a filter driver, `core.worktree`,
  `core.attributesFile`, `core.excludesFile`, any `include` or `includeIf`, or any per-worktree configuration.
- Reads Git metadata outside the project root only when you pass `--allow-external-git-metadata`.
- Reads files only inside the project root, after following symlinks and junctions. Rejects `..`, absolute paths,
  drive letters, colons (alternate data streams) and reserved Windows device names.
- Writes nothing. Output goes to standard output only.

## 3. Guidance for people who run Siftelo

1. **Clone before you check.** If the repository is not yours, clone it into a new folder and point Siftelo at the
   clone. Delete the clone afterwards.
2. **Keep the default boundary.** Do not pass `--allow-external-git-metadata` unless you created the linked
   worktree or separate Git directory yourself and you trust it.
3. **Run as a normal user.** Do not run Siftelo as an administrator, and do not run it with privileges you would
   not give an unknown script.
4. **Treat the report as data.** Handoff text and file names come from whoever wrote the handoff and the
   repository. Read a report before you paste it into a terminal, a chat or a ticket.
5. **Check a report before you share it.** Reports contain absolute local paths, the branch name, changed file
   names (up to 200) and quoted handoff lines. See `PRIVACY.md`.
6. **Do not put secrets in a handoff.** Tokens, passwords, private URLs and customer data must never be written
   into a handoff or a manifest.
7. **Do not rely on exit code 0.** It means no contradiction was found by these checks. It is not verified
   readiness and it authorises nothing.

## 4. Known residual risks (beta)

These are known and not fixed. They are listed in full in `LIMITATIONS.md`.

- **Memory from hostile Git output (L-04).** Git's output is read in chunks and capped while it is read. When the
  cap or the 10-second timeout is reached, the Git process is killed and reaped. Two independent model reviews of
  the TRC-010 changes found issues, and all the parser and start-up defects they raised were fixed and tested.
  **No human has reviewed the code.**
- **Windows helper processes (L-17).** Windows kills only the direct child. An unusual helper process could outlive
  it. The allowlisted commands start no helpers because fsmonitor and the untracked cache are disabled.
- **Terminal control characters (L-05, L-16, L-20).** The Markdown report shows control characters, line breaks,
  bidirectional controls and backticks as visible escapes. JSON output is escaped. Some invisible characters are
  not escaped; use JSON for exact bytes.
- **Time-of-check to time-of-use (L-11).** A local process with write access to the project can change paths
  between the check and the read.
- **Windows executable lookup (L-10).** On the tested Windows setup, a `git.exe` placed in the current directory
  was not used in a probe. This was tested once and is not a guarantee for other setups.

## 5. Reporting a vulnerability

Report privately through GitHub Private Vulnerability Reporting on the repository, as described in `SECURITY.md`.
The owner must enable and verify this feature before public release. Until then, do not publish details of a
security problem anywhere.

Private beta testers: use the private channel that the owner agrees with you separately.

Do not send private repositories, real handoffs, reports that contain paths or names, or any secret. Use a minimal
synthetic reproduction, and state the Siftelo version, the install route, the operating system, and the Python and
Git versions.

The owner sets acknowledgement times, severity decisions and disclosure timing.
