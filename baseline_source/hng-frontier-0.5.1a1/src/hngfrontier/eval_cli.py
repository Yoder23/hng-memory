"""Installed dispatcher for the repository's auditable evaluation command surface."""

from __future__ import annotations

import argparse
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Sequence


RELATIVE_RUNNER = Path("breakthrough_eval") / "scripts" / "reproduce.py"


def resolve_repo_root(explicit: Path | None, *, cwd: Path | None = None) -> Path:
    if explicit is not None:
        candidates = [explicit]
    else:
        start = (cwd or Path.cwd()).resolve()
        candidates = [start, *start.parents]
    for candidate in candidates:
        root = candidate.resolve()
        if (root / RELATIVE_RUNNER).is_file():
            return root
    location = str(explicit) if explicit is not None else str(cwd or Path.cwd())
    raise FileNotFoundError(
        f"no HNG Frontier evaluation checkout found from {location!r}; "
        "pass --repo-root PATH containing breakthrough_eval/scripts/reproduce.py"
    )


def command_for(repo_root: Path, forwarded: Sequence[str]) -> list[str]:
    runner = repo_root / RELATIVE_RUNNER
    if not runner.is_file():
        raise FileNotFoundError(f"evaluation runner is missing: {runner}")
    return [sys.executable, str(runner), *forwarded]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="hng-eval",
        description="Dispatch to a verified HNG Frontier repository's breakthrough evaluation runner.",
    )
    result.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root; otherwise search the current directory and its parents.",
    )
    result.add_argument("--version", action="version", version=f"%(prog)s {version('hng-frontier')}")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args, forwarded = parser().parse_known_args(argv)
    if not forwarded:
        parser().print_help()
        return 0
    try:
        root = resolve_repo_root(args.repo_root)
        command = command_for(root, forwarded)
    except FileNotFoundError as error:
        print(f"hng-eval: {error}", file=sys.stderr)
        return 2
    completed = subprocess.run(command, cwd=root, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
