# Siftelo 0.1.0 early beta: limitations and open issues

Claims here reflect what was tested. Anything not listed as tested is untested.

## 1. Tested and untested

| item | status |
|---|---|
| Python | **Tested:** 3.13.3 on Windows 11; 3.13.5 on Linux (independent review, TRC-014A). **Tested on GitHub-hosted runners:** 3.11, 3.12 and 3.13 on Windows and Ubuntu (TRC-017, one manual run, all six jobs passed). **Not run on a local machine:** 3.11 and 3.12. |
| Git | **Tested:** 2.52.0 on Windows 11; 2.47.3 on Linux (independent review). **Untested:** the 2.32 minimum, and every other version. |
| Operating system | **Tested:** Windows 11 (this workspace) and Linux (independent review, TRC-014A). **macOS:** not run. Linux results were not produced in this workspace. |
| Test suite | **Windows 11, Python 3.13.3, Git 2.52.0:** 227 tests, all passed. **Linux, Python 3.13.5, Git 2.47.3 (independent review):** 226 passed, 1 skipped (Windows-specific), 0 failures. |
| Source distribution | The extracted sdist passes the full suite (227 tests) and builds a wheel that matches the clean-copy wheel (TRC-013 and TRC-014). |
| Wheel | Built reproducibly on Windows 11 with setuptools 84.2.1 (same hash across two clean builds; TRC-016B). The hosted Linux build and the CRLF-checkout Windows build give different hashes (TRC-017; see L-25). The earlier 80.9.0 build has a different hash and is superseded. Installed offline into a fresh virtual environment. |
| Demonstration | Both synthetic builds exit 3 (correct) and 1 (stale), through the installed command. |

## 2. Known limitations (documented)

- **Not a sandbox.** See `SECURITY-GUIDANCE.md`.
- **Fail-closed false positives.** Repositories with `extensions.worktreeConfig`, filters (for example Git LFS),
  includes or alternates get no working-tree status. Results may look noisier than the repository is.
- **Submodules are not inspected.**
- **Alternates are always treated as external metadata.** Some forks and `--reference` clones need approval.
- **Heuristic prose parsing.** Test-success claims are detected by pattern. A real claim phrased unusually is
  missed. `Pending approval:` detection depends on its exact prefix.
- **Blockers are read only from exact `Blocked:` / `Blocker:` lines,** including unchecked task items (`- [ ]`).
  Checked tasks (`- [x]`) are surfaced for review and are never active. Free-form blocker language is not inferred.
  A blocker resolved elsewhere still shows until the handoff is edited. Stacked markers (`- - Blocked:`) are not read.
- **Code is skipped, with simplified rules.** Fenced blocks and four-space indented blocks are not read. The rules
  follow CommonMark for the constructs a handoff uses, not for every construct.
- **Link checks confirm existence only.** Content is not read.
- **Dirty trees are `unknown`.** Handoffs kept in the working tree produce review items.
- **Git versions.** See section 1 and `INSTALLATION.md`.

## 3. Open issues

Priority meanings:

- **A** = must be resolved, or the claim must be narrowed, before an external beta.
- **B** = should be resolved before a public release.
- **C** = later.

| ID | Priority | Status (0.1.0 early beta) | Issue | Proposed action |
|---|---|---|---|---|
| L-01 | A | **Done.** Apache-2.0 selected; `LICENSE`, `NOTICE` and SPDX metadata added. Copyright notice set to `Copyright 2026 Marsh` (owner-approved). **Good-faith rights and provenance confirmation recorded** (not an absolute warranty). | None open. | See section 5 of `LICENSING.md`. |
| L-02 | A | **Partly.** Owner-reported: GitHub and preliminary web checks found no obvious exact-name conflict. PyPI and npm: no project or package named `siftelo` at the 2026-11-25 checks. Trademark, checked 2026-11-25: EUIPO basic word search for `siftelo` returned no trade marks (a control search for `apple` returned results, so the search worked). UK IPO similar-word search, first page of five (44 results in total): registered similar marks include FINTELO (UK00906632459, Classes 9, 41 and 42) and several SOFTEL marks; the other pages were not reviewed. USPTO word search returned no result. IP India and WIPO Global Brand Database were not searched: the WIPO page showed a verification challenge, which was not bypassed. SIFTIA (Classes 42 and 35, owner MiWeb LLC) needs professional review. **Open.** | Name `Siftelo` not cleared for trademark use; FINTELO and SIFTIA need professional review. | Owner-led checks, including the IP India and WIPO searches, and professional review before any public listing or commercial use. |
| L-06 | B | Open (documented as untested). | The Git 2.32 minimum is a design target, not a tested floor. | Test an older Git, or narrow the claim. |
| L-08 | B | **Hosted-tested (TRC-017).** Python 3.11 and 3.12 passed the full driver on GitHub-hosted Windows and Ubuntu runners. Not run on a local machine. | The hosted evidence covers one commit and one manual run. | Run the hosted matrix again for each release candidate. |
| L-09 | B | **Addressed.** This repository holds no historical archives or `handoff.md`; neither is in the sdist or the wheel. | None in this repository. | Keep development material out of any release package. |
| L-10 | B | Open (watch item). | Windows executable lookup from the current directory. One probe did not reproduce it. | Keep as a watch item. Resolving `git` to a full path once at start is a possible follow-up. |
| L-11 | C | Open. | Time-of-check to time-of-use between the metadata check and the Git run. | Document only. |
| L-12 | C | Open. | Only `worktreeConfig` is audited among `extensions.*` keys. | Document only. |
| L-13 | C | Open. | Reports include absolute local paths and changed file names. | Consider a redaction option after the beta. |
| L-14 | C | **Open.** GitHub Private Vulnerability Reporting is the planned channel (`SECURITY.md`). It must be enabled and verified before public release. | Private vulnerability reporting is not verified: the GitHub endpoint returned 404 while the repository was private (checked 2026-11-25). No code of conduct. | Owner enables and verifies the feature before public release. |
| L-15 | B | Open (narrowed by TRC-010). | Untrusted prose escapes square brackets and angle brackets, but not emphasis, table pipes or HTML entities. In a terminal the risk is cosmetic. | Decide whether the report stays terminal-only. If not, escape the remaining Markdown punctuation. |
| L-16 | C | Open. | Escapes are visible text, so a literal `\x1b` looks the same as an escaped ESC. | Accept for a human-read report. Use JSON when exact bytes matter. |
| L-17 | B | Open. | On Windows only the direct Git child is killed. A helper process that inherits the output pipe could keep the reader blocked. The allowlisted commands start no helpers. | Accept for beta and document. Job Objects would be an architectural change. |
| L-18 | B | Open. | HTML comments, setext heading underlines, and headings indented one to three spaces are not modelled by the line scanner. | Document. Model later, with tests, if wanted. |
| L-19 | B | Partly addressed (TRC-011: checkboxes). | Stacked markers (`- - Blocked: x`, `- > Blocked: x`) are not read. This is a false negative. | Owner decision on stacked markers. |
| L-20 | C | Open. | Some invisible or visually altering characters are shown as they are. Bare URLs are not neutralised in prose. | Accept for a human-read terminal report. |
| L-21 | A | **Updated.** The CI workflow is manual-only, in `.github/workflows/`. Its first hosted run (run 45613575986) passed all six jobs. Actions are pinned to full commit SHAs (checkout v7.0.1, setup-python v7.1.0, both node24); their code was inspected statically, not owner-reviewed. The install uses setuptools 84.2.1, hash-checked and binary only, and `pyproject.toml` requires 84.1.0 or newer. Hosted runs are limited to the zero-spend, no-payment-method account: Actions stops once the included compute is used, rather than billing. | One manual hosted run has passed (run 45613575986) and has not been repeated; the pins are not yet owner-reviewed. | See `CI-PLAN.md` and `proposed-ci/`. Owner reviews the pinned code. |
| L-22 | B | **New.** Version `0.1.0` is a plain release number. No pre-release suffix (for example `0.1.0b1`) was applied. | Owner decision on version naming. | Owner decides before any upload, since the suffix changes file names. |
| L-23 | B | **New.** Source distribution archive bytes are not reproducible (member contents and names are). | A gzip timestamp and generated metadata carry build time. | Accept and report the content hash, as TRC-013 recommended. |
| L-24 | B | **New.** The JSON `schema` string and the module, command and distribution names changed (TraceCue to Siftelo). | Consumers that match them must update. | Documented in `README.md` ("Name and compatibility"). |
| L-25 | B | **New (TRC-019).** Wheel bytes depend on the checkout's line endings. The hosted Windows wheel (CRLF checkout) differs from the Linux hosted wheel and from the LF build. The canonical release wheel is built from LF source. | A rebuild from a CRLF Windows checkout gives a different wheel hash. | Publish checksums for the canonical wheel and document the difference. A line-ending policy needs its own approval. |

## 4. Not in scope

No MCP adapter, database, dashboard, cloud sync, test execution, or readiness certification.
