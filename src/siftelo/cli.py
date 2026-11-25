"""Command-line entry point. Read-only: the report is written to stdout only.

There is deliberately no --output option. Redirect stdout if a file is needed,
for example `siftelo ... > report.md`. Redirection is the caller's own
explicit choice; the tool itself never writes a file.

Exit codes:
  0  no contradiction detected (NOT verified readiness)
  1  contradiction found (a stale or rejected item)
  2  input error: the handoff or manifest could not be processed, or bad usage
  3  review required: nothing contradicted, but items are unknown, unverified or pending
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .preflight import run_preflight
from .report import to_json, to_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="siftelo",
        description="Read-only check of whether a Markdown handoff still matches the repository.",
        epilog="Exit codes: 0 no contradiction (not verified readiness), 1 contradiction, "
               "2 input error, 3 review required.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--project-root", required=True, type=Path,
                        help="approved project root. Project content (handoff, links, evidence, manifest) "
                             "is read only inside it. Git metadata may lie outside it only when "
                             "--allow-external-git-metadata is given, which widens that boundary.")
    parser.add_argument("--handoff", required=True, type=Path,
                        help="Markdown handoff file, relative to --project-root (or absolute inside it)")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="optional JSON manifest, relative to --project-root (or absolute inside it)")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown",
                        help="output format written to stdout (default: markdown)")
    parser.add_argument("--allow-external-git-metadata", action="store_true",
                        help="approve Git metadata that lives outside the project root (linked worktrees, "
                             "--separate-git-dir). Off by default: such metadata is reported as unknown. "
                             "Approval still runs the full configuration audit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_preflight(args.project_root, args.handoff, args.manifest,
                           allow_external_git_metadata=args.allow_external_git_metadata)
    text = to_json(report) if args.format == "json" else to_markdown(report)
    sys.stdout.write(text)
    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
