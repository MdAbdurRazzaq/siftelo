"""Optional JSON manifest with machine-readable evidence anchors.

Schema (version 1). Every object is strict: unknown keys are rejected at every
level, so a misspelled field (for example `sha_256`) fails loudly instead of
silently disabling a check. Types are exact: `schema_version` must be the
integer 1 (`true` and `1.0` are rejected).

{
  "schema_version": 1,
  "repository": {"expected_head": "<hex, 7-40>", "expected_branch": "<name>"},
  "evidence": [
    {"path": "relative/path.txt", "sha256": "<64 hex>", "label": "optional"}
  ],
  "approvals": [
    {"id": "publication", "description": "optional", "status": "pending" | "granted"}
  ],
  "claims": [
    {"id": "tests-1", "text": "...", "status": "agent_reported" | "verified_metadata"}
  ]
}

A `granted` approval is recorded as a claim of the manifest author. It never
authorises an action; this tool does not verify approvals.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_MANIFEST_BYTES = 512 * 1024
SUPPORTED_VERSION = 1

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_TOP_KEYS = {"schema_version", "repository", "evidence", "approvals", "claims"}
_REPOSITORY_KEYS = {"expected_head", "expected_branch"}
_EVIDENCE_KEYS = {"path", "sha256", "label"}
_APPROVAL_KEYS = {"id", "description", "status"}
_CLAIM_KEYS = {"id", "text", "status"}
_APPROVAL_STATUS = {"pending", "granted"}
_CLAIM_STATUS = {"agent_reported", "verified_metadata"}


class ManifestError(ValueError):
    """The manifest is unreadable, malformed, or violates the schema."""


@dataclass
class EvidenceEntry:
    path: str
    sha256: str | None
    label: str | None = None


@dataclass
class ApprovalEntry:
    id: str
    description: str
    status: str


@dataclass
class ClaimEntry:
    id: str
    text: str
    status: str


@dataclass
class Manifest:
    expected_head: str | None = None
    expected_branch: str | None = None
    evidence: list[EvidenceEntry] = field(default_factory=list)
    approvals: list[ApprovalEntry] = field(default_factory=list)
    claims: list[ClaimEntry] = field(default_factory=list)


def _object(value: Any, where: str, allowed: set[str]) -> dict:
    if not isinstance(value, dict):
        raise ManifestError(f"{where} must be an object")
    unknown = set(value) - allowed
    if unknown:
        raise ManifestError(f"{where} has unknown fields: {sorted(unknown)}; allowed: {sorted(allowed)}")
    return value


def _string(obj: dict, key: str, where: str, *, required: bool) -> str | None:
    if key not in obj:
        if required:
            raise ManifestError(f"{where}.{key} is required")
        return None
    value = obj[key]
    if not isinstance(value, str):
        raise ManifestError(f"{where}.{key} must be a string")
    if required and not value.strip():
        raise ManifestError(f"{where}.{key} must not be empty")
    return value


def _array(root: dict, key: str) -> list:
    if key not in root:
        return []
    value = root[key]
    if not isinstance(value, list):
        raise ManifestError(f"{key} must be an array")
    return value


def _enum(obj: dict, key: str, where: str, allowed: set[str]) -> str:
    value = _string(obj, key, where, required=True)
    assert value is not None
    if value not in allowed:
        raise ManifestError(f"{where}.{key} must be one of {sorted(allowed)}")
    return value


def parse_manifest_text(text: str) -> Manifest:
    if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"manifest exceeds {MAX_MANIFEST_BYTES} bytes")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"malformed JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    root = _object(data, "manifest", _TOP_KEYS)

    version = root.get("schema_version")
    if type(version) is not int or version != SUPPORTED_VERSION:
        raise ManifestError(f"schema_version must be the integer {SUPPORTED_VERSION}")

    manifest = Manifest()

    if "repository" in root:
        repo = _object(root["repository"], "repository", _REPOSITORY_KEYS)
        head = _string(repo, "expected_head", "repository", required=False)
        if head is not None:
            head = head.lower()
            if not _SHA_RE.match(head):
                raise ManifestError("repository.expected_head must be a 7-40 character hex revision")
        manifest.expected_head = head
        manifest.expected_branch = _string(repo, "expected_branch", "repository", required=False)

    for i, item in enumerate(_array(root, "evidence")):
        where = f"evidence[{i}]"
        obj = _object(item, where, _EVIDENCE_KEYS)
        path = _string(obj, "path", where, required=True)
        sha = _string(obj, "sha256", where, required=False)
        if sha is not None:
            sha = sha.lower()
            if not _SHA256_RE.match(sha):
                raise ManifestError(f"{where}.sha256 must be 64 hex characters")
        manifest.evidence.append(EvidenceEntry(
            path=path or "", sha256=sha, label=_string(obj, "label", where, required=False)))

    for i, item in enumerate(_array(root, "approvals")):
        where = f"approvals[{i}]"
        obj = _object(item, where, _APPROVAL_KEYS)
        manifest.approvals.append(ApprovalEntry(
            id=_string(obj, "id", where, required=True) or "",
            description=_string(obj, "description", where, required=False) or "",
            status=_enum(obj, "status", where, _APPROVAL_STATUS),
        ))

    for i, item in enumerate(_array(root, "claims")):
        where = f"claims[{i}]"
        obj = _object(item, where, _CLAIM_KEYS)
        manifest.claims.append(ClaimEntry(
            id=_string(obj, "id", where, required=True) or "",
            text=_string(obj, "text", where, required=True) or "",
            status=_enum(obj, "status", where, _CLAIM_STATUS),
        ))

    return manifest


def load_manifest(path: Path) -> Manifest:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ManifestError(f"cannot read manifest: {exc.strerror or exc}") from exc
    if size > MAX_MANIFEST_BYTES:
        raise ManifestError(f"manifest exceeds {MAX_MANIFEST_BYTES} bytes")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestError("manifest is not valid UTF-8") from exc
    return parse_manifest_text(text)
