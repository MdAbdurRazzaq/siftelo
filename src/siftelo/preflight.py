"""Preflight orchestration: compare a Markdown handoff with the real repository.

Statuses (most important first when sorting):
  stale              a reference or recorded fact contradicts the repository now
  rejected           a reference points outside the approved root (not followed)
  unknown            the tool cannot establish the fact (detached HEAD, dirty tree,
                     pending approval, config that blocks inspection, ...)
  agent_reported     an author's claim, an author-reported blocker (``Blocked:``/``Blocker:``)
                     or a manifest-recorded approval; NOT verified
  verified_metadata  a fact checked against repository metadata or a file's
                     existence/hash. Test outcomes are never verified_metadata.

Readiness outcomes (see `_readiness`):
  error                    the handoff or manifest could not be processed (exit 2)
  contradiction_found      a stale or rejected finding exists (exit 1)
  review_required          nothing contradicted, but unknown items, approvals or
                           unverified claims need a human (exit 3)
  no_contradiction_detected the checks found no contradiction (exit 0). This is
                           NOT verified readiness and authorises nothing.

The tool never executes project tests, never writes to the repository or
anywhere else, and never reads files outside the approved root.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import gitinspect
from .handoff import HandoffDocument, Reference, parse_handoff
from .manifest import Manifest, ManifestError, load_manifest
from .paths import PathSafetyError, resolve_within

MAX_HASH_BYTES = 50 * 1024 * 1024
MAX_HANDOFF_BYTES = 1024 * 1024
MAX_FINDINGS = 500
MAX_TEXT = 300

STATUS_ORDER = {"stale": 0, "rejected": 1, "unknown": 2, "agent_reported": 3, "verified_metadata": 4}

EXIT_CODES = {"no_contradiction_detected": 0, "contradiction_found": 1, "error": 2, "review_required": 3}


@dataclass
class Finding:
    status: str
    category: str  # repository | evidence | reference | approval | claim | manifest | handoff
    subject: str
    message: str
    evidence: str  # file:line or manifest path, used as an evidence reference
    suggestion: str | None = None

    def sort_key(self) -> tuple:
        return (STATUS_ORDER[self.status], self.category, self.subject, self.message, self.evidence)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "category": self.category,
            "subject": self.subject,
            "message": self.message,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
        }


@dataclass
class PreflightReport:
    project_root: str
    handoff: str
    manifest: str | None
    repository: dict = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    truncated: bool = False

    def counts(self) -> dict[str, int]:
        out = {k: 0 for k in STATUS_ORDER}
        for f in self.findings:
            out[f.status] += 1
        return out

    def readiness(self) -> dict:
        return _readiness(self)

    def exit_code(self) -> int:
        return EXIT_CODES[self.readiness()["outcome"]]


def _readiness(report: PreflightReport) -> dict:
    counts = report.counts()
    reasons: list[str] = []
    if report.errors:
        outcome = "error"
        reasons.append(f"{len(report.errors)} input error(s); nothing was checked")
    elif counts["stale"] or counts["rejected"]:
        outcome = "contradiction_found"
        if counts["stale"]:
            reasons.append(f"{counts['stale']} stale finding(s)")
        if counts["rejected"]:
            reasons.append(f"{counts['rejected']} rejected reference(s)")
    else:
        approval_unknown = [f for f in report.findings if f.category == "approval" and f.status == "unknown"]
        other_unknown = [f for f in report.findings if f.status == "unknown" and f.category != "approval"]
        blockers = [f for f in report.findings if f.category == "blocker"]
        checked = [f for f in report.findings if f.category == "task_done"]
        unverified = counts["agent_reported"] - len(blockers) - len(checked)
        if counts["unknown"] or counts["agent_reported"]:
            outcome = "review_required"
            if other_unknown:
                reasons.append(f"{len(other_unknown)} item(s) could not be established")
            if approval_unknown:
                reasons.append(f"{len(approval_unknown)} approval item(s) pending or unrecorded (not authorisation)")
            if unverified:
                reasons.append(f"{unverified} unverified claim(s) or recorded approval(s)")
            if blockers:
                reasons.append(f"{len(blockers)} unresolved blocker(s) recorded by the author (not verified)")
            if checked:
                reasons.append(f"{len(checked)} checked item(s) marked done by the author (not verified as resolved)")
        else:
            outcome = "no_contradiction_detected"
            reasons.append("no stale, rejected, unknown or unverified items were found")
    return {
        "outcome": outcome,
        "verified_readiness": False,
        "authorizes_actions": False,
        "reasons": reasons,
    }


def _clip(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 3] + "..."


def _sha256_file(path: Path) -> tuple[str | None, str | None]:
    """Return (digest, note). digest is None when the file is too large."""
    try:
        if path.stat().st_size > MAX_HASH_BYTES:
            return None, f"file exceeds {MAX_HASH_BYTES} bytes; hash not computed"
    except OSError as exc:
        return None, f"cannot stat file: {exc.strerror or exc}"
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest(), None


def _check_repository(report: PreflightReport, root: Path, handoff: HandoffDocument,
                      manifest: Manifest | None, findings: list[Finding],
                      allow_external_git_metadata: bool = False) -> None:
    repo = gitinspect.inspect_repository(root, allow_external_git_metadata=allow_external_git_metadata)
    report.repository = {
        "is_repo": repo.is_repo,
        "root": repo.root,
        "head": repo.head,
        "branch": repo.branch,
        "git_dir": repo.git_dir,
        "common_dir": repo.common_dir,
        "blocked_reason": repo.blocked_reason,
        "status_inspected": repo.status_inspected,
        "status_skip_reason": repo.status_skip_reason,
        "dirty": repo.dirty,
        "changed_files": [{"status": c.status, "path": c.path} for c in repo.changed_files],
        "changed_files_truncated": repo.changed_files_truncated,
        "notes": repo.notes,
    }
    if not repo.is_repo:
        findings.append(Finding("unknown", "repository", "git", "project root is not an inspectable Git repository",
                                "repository", "Point --project-root at a directory that holds its own .git."))
        return
    if repo.blocked_reason:
        # Trust boundary: nothing beyond discovery was run, so no revision or status claim is made.
        findings.append(Finding("unknown", "repository", "git-metadata", _clip(repo.blocked_reason),
                                "repository", "Review the metadata location; approve it explicitly if it is expected."))
        return

    if repo.root and Path(repo.root).resolve() != root.resolve():
        # HEAD, branch and status belong to the enclosing repository. Comparing the handoff
        # against them would be a guess, so no revision check is made: the result is unknown.
        findings.append(Finding("unknown", "repository", "root",
                                f"project root {root} is inside repository {repo.root}",
                                "repository", "Pass the repository root explicitly if this is unintended."))
        findings.append(Finding("unknown", "repository", "working-tree",
                                "revision and working-tree checks skipped: project root is not the repository root",
                                "repository", "Run the preflight from the repository root."))
        return

    expected_heads = []
    if manifest and manifest.expected_head:
        expected_heads.append(("manifest", manifest.expected_head, "manifest:repository.expected_head"))
    if handoff.head:
        expected_heads.append(("handoff", handoff.head, f"handoff:{handoff.head_line}"))
    if not expected_heads:
        findings.append(Finding("unknown", "repository", "head", "no expected revision recorded",
                                "handoff", "Add a 'HEAD: <sha>' line or a manifest expected_head."))
    for source, expected, evidence in expected_heads:
        if repo.head is None:
            findings.append(Finding("unknown", "repository", "head", "HEAD could not be resolved",
                                    evidence, "Check that the repository has at least one commit."))
        elif repo.head.lower().startswith(expected.lower()) or expected.lower().startswith(repo.head.lower()):
            findings.append(Finding("verified_metadata", "repository", "head",
                                    f"{source} revision {expected[:12]} matches HEAD {repo.head[:12]}",
                                    evidence))
        else:
            findings.append(Finding("stale", "repository", "head",
                                    f"{source} expects {expected[:12]} but HEAD is {repo.head[:12]}",
                                    evidence, "Re-read the handoff against the current HEAD before continuing."))

    # Each explicit source is checked independently against the repository, as HEAD is above.
    # A conflicting handoff branch is therefore reported, never silently ignored.
    branch_sources: list[tuple[str, str, str]] = []
    if manifest and manifest.expected_branch:
        branch_sources.append(("manifest", manifest.expected_branch, "manifest:repository.expected_branch"))
    if handoff.branch and handoff.branch_line:
        branch_sources.append(("handoff", handoff.branch, f"handoff:{handoff.branch_line}"))
    if not branch_sources:
        findings.append(Finding("unknown", "repository", "branch", "no expected branch recorded",
                                "handoff", "Add a 'Branch: <name>' line or a manifest expected_branch."))
    for source, expected_branch, evidence in branch_sources:
        if repo.branch is None:
            findings.append(Finding("unknown", "repository", "branch",
                                    f"current branch is unresolved (HEAD is detached); {source} expects {expected_branch!r}",
                                    evidence, "Check out the expected branch or record the detached state."))
        elif repo.branch == expected_branch:
            findings.append(Finding("verified_metadata", "repository", "branch",
                                    f"{source} branch {expected_branch!r} matches current branch {repo.branch!r}",
                                    evidence))
        else:
            findings.append(Finding("stale", "repository", "branch",
                                    f"{source} expects branch {expected_branch!r} but current branch is {repo.branch!r}",
                                    evidence, "Switch to the expected branch manually, then re-run preflight."))

    if not repo.status_inspected:
        reason = repo.status_skip_reason or "working-tree status unavailable"
        findings.append(Finding("unknown", "repository", "working-tree",
                                _clip(f"working-tree status not inspected: {reason}"),
                                "repository",
                                "Review the repository configuration manually; uncommitted state is unknown."))
    elif repo.dirty:
        shown = ", ".join(f"{c.status.strip() or c.status}:{c.path}" for c in repo.changed_files[:10])
        more = " (truncated)" if repo.changed_files_truncated or len(repo.changed_files) > 10 else ""
        findings.append(Finding("unknown", "repository", "working-tree",
                                _clip(f"{len(repo.changed_files)} changed or untracked path(s){more}: {shown}"),
                                "repository",
                                "Uncommitted changes are not covered by the recorded revision; review them."))


def _resolve_link(root: Path, handoff_rel: str, target: str) -> Path:
    """Resolve a Markdown link relative to the handoff's own directory, inside `root` only."""
    if target.startswith(("/", "\\")) or PurePosixPath(target).is_absolute():
        raise PathSafetyError(f"absolute link target rejected: {target!r}")
    base = PurePosixPath(handoff_rel).parent.as_posix()
    joined = posixpath.normpath(posixpath.join(base, target.replace("\\", "/")))
    if joined == ".." or joined.startswith("../"):
        raise PathSafetyError(f"link escapes approved root: {target!r}")
    return resolve_within(root, joined)


def _check_one_reference(root: Path, handoff_rel: str, ref: Reference, findings: list[Finding]) -> None:
    evidence = f"handoff:{ref.line}"
    try:
        if ref.kind == "link":
            resolved = _resolve_link(root, handoff_rel, ref.target)
        else:
            resolved = resolve_within(root, ref.target)
    except PathSafetyError as exc:
        findings.append(Finding("rejected", "reference", ref.target, _clip(str(exc)), evidence,
                                "Use a path inside the project root."))
        return
    if not resolved.exists():
        findings.append(Finding("stale", "reference", ref.target,
                                "referenced path does not exist", evidence,
                                "Update or remove the reference in the handoff."))
    elif resolved.is_dir():
        findings.append(Finding("unknown", "reference", ref.target,
                                "referenced path is a directory; not inspected", evidence))
    else:
        findings.append(Finding("verified_metadata", "reference", ref.target,
                                "referenced file exists", evidence))


def _check_references(root: Path, handoff: HandoffDocument, handoff_rel: str,
                      findings: list[Finding]) -> None:
    for ref in handoff.references:
        _check_one_reference(root, handoff_rel, ref, findings)


def _check_manifest_evidence(root: Path, manifest: Manifest, findings: list[Finding]) -> None:
    for i, entry in enumerate(manifest.evidence):
        evidence = f"manifest:evidence[{i}]"
        try:
            resolved = resolve_within(root, entry.path)
        except PathSafetyError as exc:
            findings.append(Finding("rejected", "evidence", entry.path, _clip(str(exc)), evidence,
                                    "Use a repository-relative path inside the project root."))
            continue
        if not resolved.is_file():
            findings.append(Finding("stale", "evidence", entry.path, "evidence file is missing", evidence,
                                    "Regenerate the evidence file or correct the manifest path."))
            continue
        if entry.sha256 is None:
            findings.append(Finding("verified_metadata", "evidence", entry.path,
                                    "evidence file exists; no hash recorded", evidence))
            continue
        digest, note = _sha256_file(resolved)
        if digest is None:
            findings.append(Finding("unknown", "evidence", entry.path, note or "hash unavailable", evidence))
        elif digest == entry.sha256:
            findings.append(Finding("verified_metadata", "evidence", entry.path,
                                    "SHA-256 matches manifest", evidence))
        else:
            findings.append(Finding("stale", "evidence", entry.path,
                                    f"SHA-256 mismatch: recorded {entry.sha256[:12]}, actual {digest[:12]}",
                                    evidence, "The evidence changed after it was recorded; re-review it."))


def _check_claims_and_approvals(handoff: HandoffDocument, manifest: Manifest | None,
                                findings: list[Finding]) -> None:
    for claim in handoff.test_claims:
        findings.append(Finding("agent_reported", "claim", f"handoff:{claim.line}",
                                _clip(f"test-success claim in prose (not executed or verified): {claim.text}"),
                                f"handoff:{claim.line}",
                                "Run the tests yourself or attach a captured test log with a hash."))
    if manifest:
        for claim in manifest.claims:
            if claim.status == "verified_metadata":
                findings.append(Finding("unknown", "claim", claim.id,
                                        "manifest marks this claim verified_metadata; this tool cannot verify "
                                        "claims beyond metadata", f"manifest:claims[{claim.id}]"))
            else:
                findings.append(Finding("agent_reported", "claim", claim.id, _clip(claim.text),
                                        f"manifest:claims[{claim.id}]"))

    for item in handoff.pending_approvals:
        findings.append(Finding("unknown", "approval", "handoff", _clip(f"pending approval: {item.text}"),
                                f"handoff:{item.line}", "Obtain the approval before the related action."))

    approvals = manifest.approvals if manifest else []
    for approval in approvals:
        if approval.status == "pending":
            findings.append(Finding("unknown", "approval", approval.id,
                                    _clip(f"approval recorded as pending: {approval.description}"),
                                    f"manifest:approvals[{approval.id}]",
                                    "Do not perform the gated action until this is granted."))
        else:
            findings.append(Finding("agent_reported", "approval", approval.id,
                                    _clip(f"recorded as granted by the manifest author; not verified and "
                                          f"not an authorisation: {approval.description}"),
                                    f"manifest:approvals[{approval.id}]",
                                    "Verify the approval with its source before relying on it."))

    publication_recorded = any(a.id == "publication" for a in approvals)
    mentions_publication = any(
        "publish" in item.text.lower() or "publication" in item.text.lower()
        for item in handoff.pending_approvals
    )
    if mentions_publication and not publication_recorded:
        findings.append(Finding("unknown", "approval", "publication",
                                "handoff mentions publication approval but manifest records none",
                                "handoff", "Record the publication approval state in the manifest."))


def _check_blockers(handoff: HandoffDocument, findings: list[Finding]) -> None:
    """Author-reported unresolved conditions. Recorded for review; never verified or resolved here."""
    for blocker in handoff.blockers:
        findings.append(Finding("agent_reported", "blocker", "unresolved",
                                _clip(f"unresolved blocker, author-reported and not verified: {blocker.text}"),
                                f"handoff:{blocker.line}",
                                "Resolve the blocker, or record how it was resolved. This tool cannot tell "
                                "whether it still applies."))


def _check_checked_items(handoff: HandoffDocument, findings: list[Finding]) -> None:
    """Checked tasks carrying a marker: surfaced for review. Never an active blocker, never resolved."""
    for item in handoff.checked_items:
        findings.append(Finding("agent_reported", "task_done", f"handoff:{item.line}",
                                _clip(f"checked task ({item.kind}) marked done by the author; not verified "
                                      f"as resolved: {item.text}"),
                                f"handoff:{item.line}",
                                "Confirm the item is resolved and record the evidence. A ticked box is "
                                "not proof."))


def _relative_to_root(root: Path, given: str | Path, what: str) -> str:
    """Return a posix path relative to `root`, or raise ValueError when outside it."""
    path = Path(given)
    # Resolve absolute inputs first so 8.3 short names and symlinked prefixes compare correctly.
    rel = Path(os.path.realpath(path)).relative_to(root) if path.is_absolute() else path
    resolve_within(root, str(rel).replace("\\", "/"))  # containment and symlink checks
    return str(rel).replace("\\", "/")


def run_preflight(project_root: str | Path, handoff_path: str | Path,
                  manifest_path: str | Path | None = None, *,
                  allow_external_git_metadata: bool = False) -> PreflightReport:
    root = Path(project_root).resolve()
    report = PreflightReport(project_root=str(root), handoff=str(handoff_path),
                             manifest=str(manifest_path) if manifest_path else None)

    if not root.is_dir():
        report.errors.append(f"project root is not a directory: {root}")
        return report

    try:
        handoff_rel = _relative_to_root(root, handoff_path, "handoff")
    except (ValueError, PathSafetyError) as exc:
        report.errors.append(f"handoff must lie inside the project root: {exc}")
        return report
    handoff_file = root / handoff_rel
    if not handoff_file.is_file():
        report.errors.append(f"handoff not found: {handoff_path}")
        return report
    try:
        raw = handoff_file.read_bytes()
    except OSError as exc:
        report.errors.append(f"cannot read handoff: {exc.strerror or exc}")
        return report
    if len(raw) > MAX_HANDOFF_BYTES:
        report.errors.append("handoff exceeds 1 MiB")
        return report
    handoff = parse_handoff(raw.decode("utf-8", errors="replace"), handoff_rel)

    manifest = None
    if manifest_path is not None:
        try:
            manifest_rel = _relative_to_root(root, manifest_path, "manifest")
        except (ValueError, PathSafetyError) as exc:
            report.errors.append(f"manifest must lie inside the project root: {exc}")
            return report
        try:
            manifest = load_manifest(root / manifest_rel)
        except ManifestError as exc:
            report.errors.append(f"manifest rejected: {exc}")
            return report

    findings: list[Finding] = []
    _check_repository(report, root, handoff, manifest, findings, allow_external_git_metadata)
    _check_references(root, handoff, handoff_rel, findings)
    if manifest:
        _check_manifest_evidence(root, manifest, findings)
    _check_claims_and_approvals(handoff, manifest, findings)
    _check_blockers(handoff, findings)
    _check_checked_items(handoff, findings)
    for warning in handoff.warnings:
        findings.append(Finding("unknown", "handoff", "metadata", _clip(warning), "handoff"))

    findings.sort(key=Finding.sort_key)
    if len(findings) > MAX_FINDINGS:
        report.truncated = True
        findings = findings[:MAX_FINDINGS]
    report.findings = findings
    return report
