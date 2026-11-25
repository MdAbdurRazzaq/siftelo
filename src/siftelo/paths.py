"""Path containment and symlink-escape checks.

Every filesystem read performed by the preflight goes through `resolve_within`.
A path is accepted only if, after resolving symlinks, it lies inside the
approved root. Anything else raises `PathSafetyError`.
"""

from __future__ import annotations

import os
from pathlib import Path


class PathSafetyError(ValueError):
    """Raised when a referenced path escapes the approved root."""


_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _components(raw: str) -> list[str]:
    # Normalise both separators so `..\x` and `docs\a.md` are handled like `/`.
    return raw.replace("\\", "/").split("/")


def _has_parent_traversal(raw: str) -> bool:
    return ".." in _components(raw)


def _check_windows_components(raw: str) -> None:
    """Reject names Windows would reinterpret (device names, streams, stripped suffixes)."""
    if ":" in raw:
        # Covers drive letters, NTFS alternate data streams (file:stream), and `::$DATA`.
        raise PathSafetyError(f"colon in path rejected: {raw!r}")
    for part in _components(raw):
        if part in ("", "."):
            continue
        if part.endswith((".", " ")):
            raise PathSafetyError(f"trailing dot or space rejected: {raw!r}")
        stem = part.split(".", 1)[0].rstrip(" ").upper()
        if stem in _WINDOWS_RESERVED:
            raise PathSafetyError(f"reserved Windows device name rejected: {raw!r}")


def resolve_within(root: Path, relative: str) -> Path:
    """Resolve `relative` against `root` and prove it stays inside `root`.

    Rejects absolute paths, parent-directory segments, drive-qualified paths,
    colons (alternate data streams), reserved Windows device names, names with
    trailing dots or spaces, and any path whose real location (after following
    symlinks and junctions) falls outside `root`. Returns the resolved path.
    """
    if not isinstance(relative, str) or not relative.strip():
        raise PathSafetyError("empty path reference")
    if "\x00" in relative:
        raise PathSafetyError("path contains NUL byte")
    if _has_parent_traversal(relative):
        raise PathSafetyError(f"parent traversal rejected: {relative!r}")
    if Path(relative).is_absolute() or os.path.isabs(relative) or relative.startswith(("/", "\\")):
        raise PathSafetyError(f"absolute path rejected: {relative!r}")
    _check_windows_components(relative)

    real_root = Path(os.path.realpath(root))
    candidate = real_root / relative
    # Walk each component and reject symlinks whose target leaves the root.
    current = real_root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            target = Path(os.path.realpath(current))
            if not _is_relative_to(target, real_root):
                raise PathSafetyError(f"symlink escape rejected: {relative!r}")
    resolved = Path(os.path.realpath(candidate))
    if not _is_relative_to(resolved, real_root):
        raise PathSafetyError(f"path escapes approved root: {relative!r}")
    return resolved


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
