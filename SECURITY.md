# Security policy

Status: applies to the 0.1.0 early beta. Private reporting must be enabled and verified before the release is announced.

Siftelo is a read-only preflight tool. It is not a sandbox: it does not make an untrusted repository safe to open,
and its results are not security decisions. Read `beta/SECURITY-GUIDANCE.md` and `beta/LIMITATIONS.md` before you
point Siftelo at a repository you do not control.

## Supported versions

Only the 0.1.0 early beta. No earlier version has been published.

## Reporting a vulnerability

Report privately through **GitHub Private Vulnerability Reporting** for this repository. Do not open a public issue,
discussion or pull request that describes a security problem.

**Activation.** The repository owner enables private vulnerability reporting in the repository's security settings
after the repository becomes public, then checks that a test report can be submitted and received. Until that check
is complete, the route may be unavailable. If you cannot use it, do not post details of the problem publicly. Contact
the repository owner through the contact route on their GitHub profile, and send only a minimal synthetic
reproduction.

Include in your report:

- the Siftelo version, the install route, the operating system, and the Python and Git versions;
- a minimal **synthetic** reproduction.

Do not send private repositories, real handoffs, reports that contain paths or names, or any secret.

## Response

The owner sets any acknowledgement times, severity decisions and disclosure timing. This release does not promise them.
