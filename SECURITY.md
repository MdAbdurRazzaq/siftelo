# Security policy

Status: draft for the 0.1.0 beta. Not yet operational.

Siftelo is a read-only preflight tool. It is not a sandbox: it does not make an untrusted repository safe to open,
and its results are not security decisions. Read `beta/SECURITY-GUIDANCE.md` and `beta/LIMITATIONS.md` before you
point Siftelo at a repository you do not control.

## Supported versions

Only the 0.1.0 beta candidate. No earlier version has been published.

## Reporting a vulnerability

Report privately through **GitHub Private Vulnerability Reporting** for this repository. Do not open a public issue,
discussion or pull request that describes a security problem.

**The feature must be enabled and verified before public release.** The owner enables it in the repository's
security settings and checks that a report can be submitted and received. Until that verification is recorded in
the release checklist, private reporting is not available, so do not publish details of a security problem anywhere.

Private beta testers: use the private reporting channel agreed with the owner separately. It is not listed here.

Include in your report:

- the Siftelo version, the install route, the operating system, and the Python and Git versions;
- a minimal **synthetic** reproduction.

Do not send private repositories, real handoffs, reports that contain paths or names, or any secret.

## Response

The owner sets acknowledgement times, severity decisions and disclosure timing. This draft does not promise them.
