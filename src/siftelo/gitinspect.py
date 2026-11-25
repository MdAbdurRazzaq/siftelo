"""Read-only Git inspection with a fail-closed trust boundary.

Threat model: the repository under inspection is untrusted. Its configuration,
including per-worktree configuration, must not be able to execute programs,
and its metadata must not silently pull the tool outside the project root.

Trust boundary (TRC-003):

* Project content and evidence paths: must resolve inside the project root.
* Git metadata: the directory that holds the repository's config, HEAD and
  objects. It may legitimately live outside the root (linked worktrees,
  `--separate-git-dir`). Such metadata is blocked unless the caller passes
  `allow_external_git_metadata=True`, which the CLI exposes as
  `--allow-external-git-metadata`.

Order of operations for one inspection:

1. Pure Python, no Git executed: the project root must contain its own `.git`
   (directory or pointer file). Upward discovery is disabled. If `.git` leads
   outside the root and the caller has not approved it, stop here (blocked).
2. `rev-parse --show-toplevel` with `GIT_CEILING_DIRECTORIES` set to the root's
   parent, so Git cannot discover an enclosing repository.
3. `rev-parse --absolute-git-dir` and `--git-common-dir`: both must lie inside
   the root unless approved. Object `alternates` are external metadata too.
4. HEAD and branch (read-only, no config-driven execution).
5. Audit of the local config and of per-worktree config. Blocked if the config
   defines filter drivers, a worktree redirection, an include directive, an
   attribute or exclude file, or enables `extensions.worktreeConfig` (per-worktree
   config is not audited, so it is not trusted).
6. `status`, with `core.fsmonitor=false`, `--no-optional-locks` and
   `--ignore-submodules=all`. Only reached if steps 1-5 pass.

Every Git call uses `shell=False`, a fixed argument vector, a timeout, a capped
output size, and a sanitised environment (see `safe_environment`).
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

GIT_TIMEOUT_SECONDS = 10
MAX_OUTPUT_BYTES = 256 * 1024
MAX_CHANGED_FILES_REPORTED = 200

_NEUTRALISING_OPTIONS = ("-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false")

# name -> argument vector (after the neutralising options). Nothing else is runnable.
_ALLOWED: dict[str, tuple[str, ...]] = {
    "toplevel": ("rev-parse", "--show-toplevel"),
    "absolute_git_dir": ("rev-parse", "--absolute-git-dir"),
    "git_common_dir": ("rev-parse", "--git-common-dir"),
    "head": ("rev-parse", "--verify", "HEAD"),
    "branch": ("symbolic-ref", "--quiet", "--short", "HEAD"),
    "local_config": ("config", "--local", "--null", "--list"),
    "status": ("--no-optional-locks", "status", "--porcelain=v1", "--untracked-files=all",
               "--ignore-submodules=all"),
}

# Local-config keys that would let status run programs, redirect the worktree,
# or read files outside the root.
_BLOCKING_PREFIXES = ("filter.", "include.", "includeif.")
_BLOCKING_KEYS = ("core.worktree", "core.attributesfile", "core.excludesfile")
_WORKTREE_CONFIG_KEY = "extensions.worktreeconfig"
_FALSEY = {"", "false", "no", "off", "0"}

# Variables that only narrow repository discovery are safe to keep. The ceiling is
# always overwritten by `safe_environment(ceiling=...)`.
_KEPT_GIT_VARIABLES = {"GIT_CEILING_DIRECTORIES"}


class GitError(RuntimeError):
    """A Git inspection command failed, timed out, or is not allowed."""


@dataclass
class ChangedFile:
    status: str  # two-character porcelain code, e.g. " M", "??"
    path: str


@dataclass
class RepoState:
    is_repo: bool
    root: str | None = None
    head: str | None = None
    branch: str | None = None  # None when detached or not a repo
    git_dir: str | None = None
    common_dir: str | None = None
    blocked_reason: str | None = None  # boundary violation: nothing beyond discovery was run
    status_inspected: bool = False
    status_skip_reason: str | None = None
    dirty: bool = False
    changed_files: list[ChangedFile] = field(default_factory=list)
    changed_files_truncated: bool = False
    notes: list[str] = field(default_factory=list)


def safe_environment(ceiling: str | None = None, base: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment with every GIT_* variable removed and config neutralised."""
    source = dict(os.environ if base is None else base)
    env = {k: v for k, v in source.items()
           if not k.upper().startswith("GIT_") or k.upper() in _KEPT_GIT_VARIABLES}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    if ceiling is not None:
        env["GIT_CEILING_DIRECTORIES"] = ceiling
    return env


def _run_git(cwd: Path, key: str) -> str:
    if key not in _ALLOWED:
        raise GitError(f"git subcommand not allowed: {key}")
    argv = ["git", *_NEUTRALISING_OPTIONS, *_ALLOWED[key]]
    try:
        stdout = run_bounded(argv, cwd=cwd, env=safe_environment(ceiling=os.path.realpath(cwd.parent)),
                             timeout=GIT_TIMEOUT_SECONDS, max_bytes=MAX_OUTPUT_BYTES)
    except GitError as exc:
        raise GitError(f"git {key}: {exc}") from exc
    return stdout.decode("utf-8", errors="replace")


_READ_CHUNK_BYTES = 64 * 1024
_KILL_WAIT_SECONDS = 5


def _kill_process(proc: subprocess.Popen) -> None:
    """Stop the child and anything in its process group, then reap it.

    On POSIX the child starts a new session, so its group can be signalled as one.
    On Windows only the direct child is terminated: Siftelo disables Git's own
    helpers (fsmonitor, untracked cache), so the direct child is the only process
    it starts for these commands.
    """
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=_KILL_WAIT_SECONDS)
    except subprocess.TimeoutExpired:
        pass  # the child could not be reaped in time; nothing more can be done safely


def run_bounded(argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float,
                max_bytes: int) -> bytes:
    """Run one fixed command and return its stdout, never holding more than `max_bytes` of it.

    A reader thread copies output in small chunks. As soon as the total passes `max_bytes`,
    or the timeout passes, the child is killed and reaped and a `GitError` is raised.
    stderr is discarded (never captured). `shell=False` and a fixed argument vector are
    always used. The caller supplies the argument vector and the environment.
    """
    options = {"start_new_session": True} if os.name == "posix" else {}
    try:
        proc = subprocess.Popen(argv, cwd=str(cwd), env=env, shell=False,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, **options)
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    except OSError as exc:
        raise GitError(f"git could not be started: {exc}") from exc

    collected = bytearray()
    outcome: dict[str, object] = {"overflow": False, "error": None}

    def reader() -> None:
        try:
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read1(_READ_CHUNK_BYTES)
                if not chunk:
                    return
                if len(collected) + len(chunk) > max_bytes:
                    outcome["overflow"] = True
                    return
                collected.extend(chunk)
        except BaseException as exc:  # recorded and raised by the caller; never silently lost
            outcome["error"] = exc

    deadline = time.monotonic() + timeout
    thread = threading.Thread(target=reader, name="siftelo-git-reader", daemon=True)
    finished = False
    try:
        thread.start()
        thread.join(timeout)
        if outcome["error"] is not None:
            raise GitError(f"could not read command output: {outcome['error']}") from outcome["error"]  # type: ignore[arg-type]
        if outcome["overflow"]:
            raise GitError(f"output exceeded {max_bytes} bytes")
        if thread.is_alive():
            raise GitError(f"command timed out after {timeout}s")
        try:
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise GitError(f"command timed out after {timeout}s") from exc
        if proc.returncode != 0:
            raise GitError(f"exited with {proc.returncode}")
        finished = True
        return bytes(collected)
    finally:
        # Any early exit (a limit, a read error, an interrupt) must stop the child.
        # A child that has already exited needs no signal.
        if not finished and proc.poll() is None:
            _kill_process(proc)
        if thread.ident is not None:
            thread.join(_KILL_WAIT_SECONDS)
        if proc.stdout is not None and not thread.is_alive():
            proc.stdout.close()


def _real(path: str | Path) -> Path:
    return Path(os.path.realpath(path))


def _inside(path: Path, root: Path) -> bool:
    try:
        _real(path).relative_to(root)
        return True
    except ValueError:
        return False


def _metadata_location(dotgit: Path) -> Path:
    """Where the repository metadata lives, read without running Git.

    A `.git` directory is its own location. A `.git` file is a pointer
    (`gitdir: <path>`), used by linked worktrees and `--separate-git-dir`.
    """
    if dotgit.is_dir():
        return _real(dotgit)
    if dotgit.is_file():
        head = dotgit.read_bytes()[:4096].decode("utf-8", errors="replace").splitlines()[:1]
        if not head or not head[0].startswith("gitdir:"):
            raise GitError("unrecognised .git pointer file")
        target = Path(head[0][len("gitdir:"):].strip())
        if not target.is_absolute():
            target = dotgit.parent / target
        return _real(target)
    raise GitError(".git is neither a directory nor a pointer file")


def blocking_local_config(root: Path, git_dir: Path, common_dir: Path) -> list[str]:
    """Return reasons the repository's configuration makes `status` unsafe to run.

    Reads config only. `--local` does not follow include directives, so an
    include is itself reported rather than followed. Per-worktree config is
    blocked two ways: an enabled `extensions.worktreeConfig`, and the presence of
    any `config.worktree` file. Either alone is enough to skip `status`.
    """
    text = _run_git(root, "local_config")
    reasons: set[str] = set()
    for entry in text.split("\0"):
        if not entry:
            continue
        head, _, value = entry.partition("\n")
        key = head.lower()
        if key == _WORKTREE_CONFIG_KEY:
            if value.strip().lower() not in _FALSEY:
                reasons.add("extensions.worktreeConfig enabled (per-worktree config is not audited)")
        elif key.startswith(_BLOCKING_PREFIXES) or key in _BLOCKING_KEYS:
            reasons.add(key)

    # Plain directory listing, not glob: brackets or stars in a real path must not hide a file.
    worktree_files = [git_dir / "config.worktree", common_dir / "config.worktree"]
    linked = common_dir / "worktrees"
    if linked.is_dir():
        worktree_files += [entry / "config.worktree" for entry in linked.iterdir() if entry.is_dir()]
    if any(os.path.lexists(p) for p in worktree_files):
        reasons.add("config.worktree present (per-worktree config is not audited)")
    return sorted(reasons)


def _parse_porcelain(text: str) -> list[ChangedFile]:
    files: list[ChangedFile] = []
    for line in text.splitlines():
        if len(line) < 4:
            continue
        code = line[:2]
        path = line[3:]
        if " -> " in path:  # rename: keep the destination path
            path = path.split(" -> ", 1)[1]
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        files.append(ChangedFile(status=code, path=path.replace("\\", "/")))
    files.sort(key=lambda f: (f.path, f.status))
    return files


def inspect_repository(project_root: Path, *, allow_external_git_metadata: bool = False) -> RepoState:
    """Inspect the Git repository at `project_root` inside the trust boundary.

    Never raises for a non-repository. Returns `RepoState` with `is_repo`,
    `blocked_reason` and `status_skip_reason` set where the boundary applies.
    """
    root = _real(project_root)
    state = RepoState(is_repo=False)

    # 1. The root must hold its own .git. No Git is executed for this check.
    dotgit = root / ".git"
    if not os.path.lexists(dotgit):
        state.notes.append("project root has no .git of its own; enclosing repositories are not used")
        return state
    try:
        metadata = _metadata_location(dotgit)
    except (GitError, OSError) as exc:
        state.is_repo = True
        state.root = str(root)
        state.blocked_reason = f"Git metadata could not be located safely: {exc}"
        return state
    state.is_repo = True
    state.root = str(root)
    if not _inside(metadata, root) and not allow_external_git_metadata:
        state.blocked_reason = (f"Git metadata lies outside the project root ({metadata}); "
                                "approve it with --allow-external-git-metadata")
        return state

    # 2. Discovery is confined to this root by GIT_CEILING_DIRECTORIES.
    try:
        toplevel = _run_git(root, "toplevel").strip()
    except GitError as exc:
        state.is_repo = False
        state.root = None
        state.notes.append(f"not inspectable as a Git repository: {exc}")
        return state
    state.root = str(Path(toplevel))
    if _real(toplevel) != root:
        return state  # preflight reports the root mismatch and skips revision checks

    # 3. Confirm the metadata locations Git itself reports.
    git_dir = _real(_run_git(root, "absolute_git_dir").strip())
    common_raw = _run_git(root, "git_common_dir").strip()
    common_dir = _real(root / common_raw if not Path(common_raw).is_absolute() else common_raw)
    state.git_dir, state.common_dir = str(git_dir), str(common_dir)
    for label, path in (("git directory", git_dir), ("common directory", common_dir)):
        if not _inside(path, root) and not allow_external_git_metadata:
            state.blocked_reason = (f"{label} lies outside the project root ({path}); "
                                    "approve it with --allow-external-git-metadata")
            return state
    alternates = common_dir / "objects" / "info" / "alternates"
    if alternates.exists() and not allow_external_git_metadata:
        state.blocked_reason = ("object alternates may read objects from outside the project root; "
                                "approve it with --allow-external-git-metadata")
        return state

    # 4. Revision metadata: read-only.
    try:
        state.head = _run_git(root, "head").strip()
    except GitError as exc:
        state.notes.append(f"HEAD could not be resolved (no commits?): {exc}")
    try:
        state.branch = _run_git(root, "branch").strip() or None
    except GitError:
        state.branch = None
        state.notes.append("HEAD is detached or branch could not be read")

    # 5. Configuration audit, before any command that could run a filter.
    try:
        blocked = blocking_local_config(root, git_dir, common_dir)
    except GitError as exc:
        state.status_skip_reason = f"local config could not be audited: {exc}"
        state.notes.append(f"working-tree status not inspected: {state.status_skip_reason}")
        return state
    if blocked:
        state.status_skip_reason = "repository config defines " + ", ".join(blocked)
        state.notes.append(f"working-tree status not inspected: {state.status_skip_reason}")
        return state

    # 6. Working-tree status, only after every check above has passed.
    try:
        files = _parse_porcelain(_run_git(root, "status"))
    except GitError as exc:
        state.notes.append(f"working-tree status unavailable: {exc}")
        return state
    state.status_inspected = True
    state.dirty = bool(files)
    if len(files) > MAX_CHANGED_FILES_REPORTED:
        state.changed_files_truncated = True
        files = files[:MAX_CHANGED_FILES_REPORTED]
    state.changed_files = files
    return state
