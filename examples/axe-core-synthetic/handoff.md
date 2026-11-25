# Handoff: accessibility scan (SYNTHETIC copy)

This is a synthetic stand-in for an accessibility-audit handoff. It is not the
real workspace and it does not reference any real repository.

Branch: audit/synthetic-axe-run
HEAD: {{HEAD}}

## Status

- Ran the axe-core scan against the synthetic fixture page.
- Results saved to `reports/axe-run.json`.
- Rule `color-contrast` reported 2 violations; both are recorded in the report.
- All tests pass and the scan is green.

## Evidence

- `reports/axe-run.json`
- `reports/summary.md`
- [scan configuration](config/axe.config.json)

## Approvals

- Pending approval: publish the audit summary as a public issue comment.
