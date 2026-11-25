# Siftelo 0.1.0 early beta: licensing, provenance and attribution

Status: licence **Apache-2.0** (owner-approved). Copyright notice **`Copyright 2026 Marsh`** (owner-approved, TRC-014A).
**Rights and provenance: good-faith confirmation by the owner** (section 5).

## 1. Decision

| item | value | source |
|---|---|---|
| Licence | Apache License, Version 2.0 (`Apache-2.0`) | owner-approved |
| Licence file | `LICENSE` in the project root, the canonical text, unmodified | see section 2 |
| Copyright notice | `Copyright 2026 Marsh`, in the `NOTICE` file and the README | owner-approved (TRC-014A) |
| Notice file | `NOTICE` in the project root; shipped in the wheel (`dist-info/licenses/`) and the sdist | this release |
| Package metadata | `license = "Apache-2.0"` and `license-files = ["LICENSE", "NOTICE"]` in `pyproject.toml` (PEP 639) | this release |
| Build backend minimum | `setuptools>=84.1.0`: 77 is the first release that accepts the expression above; 84.1.0 is the first release outside the advisories affecting earlier versions (TRC-016B) | this release |
| Intended copyright ownership | Personal. `Marsh` is the owner's public developer alias. | owner's statement |
| Rights and provenance confirmation | **Good-faith confirmation** by the owner (section 5) | owner |


## 2. The `LICENSE` file

- The file is the Apache License 2.0 text, unmodified. It has 11,357 bytes, a trailing newline, and the
  SHA-256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`.
- **Where the text came from:** no download was made. The text was copied from a licence file that is already
  installed on this machine (in the `tzdata` 2025.2 distribution). A second installed copy (in the
  `importlib_metadata` 8.0.0 distribution) has the same text, differing only by a leading blank line.
- The Apache License's appendix contains the template line `Copyright [yyyy] [name of copyright owner]`. That
  line is part of the licence text and is left as it is. The actual notice is in `NOTICE` (section 3).

## 3. Copyright notice

- The owner approved the public notice **`Copyright 2026 Marsh`** (TRC-014A). It appears in:
  - `NOTICE` (shipped in the wheel's `dist-info/licenses/` folder and in the sdist);
  - `README.md`, section "Licence and copyright" (the wheel's long description).
- Intended ownership is personal. The notice uses the public alias, not a legal name. No legal name is
  published by this project.
- Apache-2.0 does not require the notice text to be placed inside `LICENSE`; `LICENSE` stays canonical.

## 4. Audit performed (TRC-014) and third-party notices

| area | what was checked | result |
|---|---|---|
| Project source (`src/siftelo/`) | every `import` and `from` line | Only the Python standard library and the package's own modules. No vendored code, no third-party import. |
| Tests (`tests/`) | imports, copyright and licence strings, vendored folders | Standard library and the package only. No copyright or licence header found. |
| Examples (`examples/`) | content of the synthetic examples | Synthetic text. The example named `axe-core-synthetic` refers to the name of a third-party accessibility tool in a synthetic handoff, but contains no code from it. |
| Beta documents (`beta/`, root `README.md`) | written for this release | Original text. No third-party quotations. |
| Copyright and licence strings | search for `Copyright`, `License`, `Apache`, `MIT`, `BSD`, `GPL` and `SPDX` across project files | Only the licence references added in this release, and the historical records. |
| Historical archives and reports | not shipped | Not audited for licence terms beyond the search above. They are not part of any distribution. |
| Development method | the milestone reports | The reports record AI-assisted development and independent model reviews. Whether the owner holds all rights in that generated material is covered by the owner's good-faith confirmation, not an absolute warranty (section 5). |

**Third-party notices required: none.** The manual review found no third-party code, text, data or media that
needs attribution, so no third-party notice is included. If third-party material is added later, its notice must go
in `NOTICE` and its licence text in the distribution, and this section must be updated.

Not done: a licence-scanning tool was not run (none is installed, and installing one was not approved). This
audit is a manual review.

## 5. Rights and provenance confirmation

The owner has given a good-faith confirmation of rights and provenance for this release. It covers the
owner's rights in the project's code, including work produced with AI assistance that the owner directed and
reviewed, and the owner's understanding that no employer, client or other person holds rights in that code.

This is not an absolute warranty. The owner does not assert that every line of AI-assisted output is free of
third-party material. The manual audit in section 4 found no third-party material that needs a notice. If third-party
material is found later, section 4 applies: add its notice to `NOTICE`, add its licence text to the distribution,
and update this file.

The licence (Apache-2.0) and the copyright notice (`Copyright 2026 Marsh`) are final for this release.
