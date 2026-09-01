#!/usr/bin/env python3
"""Fail-closed preregistration and execution wrapper for the million-write probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts import storage_reliability_probe as bounded  # noqa: E402


EVAL = ROOT / "breakthrough_eval"
OUTPUT_DIR = EVAL / "reliability" / "million_write"
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
DATABASE = OUTPUT_DIR / "run_data" / "million_write.sqlite"
BACKUP = OUTPUT_DIR / "run_data" / "million_write_backup.sqlite"
WRAPPER = Path(__file__).resolve()
BOUNDED_PROBE = Path(bounded.__file__).resolve()
PRODUCTION_STORAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src" / "hngfrontier" / "storage_v2.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    completed = subprocess.run(
        ("git", "-c", f"safe.directory={ROOT.as_posix()}", *args),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def frozen_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "records": args.records,
        "tenants": args.tenants,
        "restart_every": args.restart_every,
        "lifecycle_records": args.lifecycle_records,
        "minimum_free_bytes": args.minimum_free_bytes,
        "journal_mode": "WAL",
        "synchronous": "FULL",
        "database": DATABASE.relative_to(ROOT).as_posix(),
        "backup": BACKUP.relative_to(ROOT).as_posix(),
        "result": RESULT.relative_to(ROOT).as_posix(),
    }


def source_hashes() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in (PROTOCOL, WRAPPER, BOUNDED_PROBE, PRODUCTION_STORAGE)
    }


def prepared_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "PREPARED_NOT_EXECUTED",
        "created_at": utc_now(),
        "config": frozen_config(args),
        "source_sha256": source_hashes(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "sqlite": sqlite3.sqlite_version,
            "cpu_count": os.cpu_count(),
        },
        "qualifying_command": [
            sys.executable,
            str(WRAPPER.relative_to(ROOT)),
            "--preregistered-commit",
            "COMMIT",
        ],
        "claim_boundary": "Preparation only; no database or behavioral result exists.",
    }


def verify_prepared(payload: Mapping[str, Any], args: argparse.Namespace) -> None:
    if payload.get("status") != "PREPARED_NOT_EXECUTED":
        raise RuntimeError("prepared status mismatch")
    if payload.get("config") != frozen_config(args):
        raise RuntimeError("prepared configuration mismatch")
    if payload.get("source_sha256") != source_hashes():
        raise RuntimeError("preregistered source hash mismatch")


def write_json(path: Path, value: Mapping[str, Any], *, exclusive: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "x" if exclusive else "w"
    with path.open(mode, encoding="utf-8", newline="\n") as handle:
        json.dump(dict(value), handle, indent=2, sort_keys=True)
        handle.write("\n")


def execute(args: argparse.Namespace) -> dict[str, Any]:
    if not PREPARED.is_file():
        raise FileNotFoundError(PREPARED)
    if RESULT.exists():
        raise FileExistsError(f"refusing to overwrite {RESULT}")
    head = git("rev-parse", "HEAD")
    if head != args.preregistered_commit:
        raise RuntimeError(f"HEAD {head} != preregistered commit {args.preregistered_commit}")
    status = git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise RuntimeError(f"execution requires a clean worktree: {status}")
    payload = json.loads(PREPARED.read_text(encoding="utf-8"))
    verify_prepared(payload, args)
    free_bytes = shutil.disk_usage(OUTPUT_DIR).free
    if free_bytes < args.minimum_free_bytes:
        raise RuntimeError(f"free bytes {free_bytes} below frozen minimum {args.minimum_free_bytes}")

    run_args = argparse.Namespace(
        records=args.records,
        tenants=args.tenants,
        restart_every=args.restart_every,
        lifecycle_records=args.lifecycle_records,
        database=DATABASE,
        backup=BACKUP,
        output=RESULT,
    )
    result = bounded.run(run_args)
    result["protocol"] = PROTOCOL.relative_to(ROOT).as_posix()
    result["prepared"] = PREPARED.relative_to(ROOT).as_posix()
    result["preregistered_commit"] = args.preregistered_commit
    result["preflight"] = {
        "clean_worktree": True,
        "source_hashes_match": True,
        "config_matches": True,
        "free_bytes_before": free_bytes,
        "minimum_free_bytes": args.minimum_free_bytes,
    }
    result["file_artifacts"] = {
        "database": {
            "bytes": DATABASE.stat().st_size,
            "sha256": sha256_file(DATABASE),
        },
        "backup": {
            "bytes": BACKUP.stat().st_size,
            "sha256": sha256_file(BACKUP),
        },
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--preregistered-commit")
    parser.add_argument("--records", type=int, default=1_000_000)
    parser.add_argument("--tenants", type=int, default=100)
    parser.add_argument("--restart-every", type=int, default=100_000)
    parser.add_argument("--lifecycle-records", type=int, default=100)
    parser.add_argument("--minimum-free-bytes", type=int, default=8_000_000_000)
    args = parser.parse_args()
    if args.prepare_only == bool(args.preregistered_commit):
        parser.error("select exactly one of --prepare-only or --preregistered-commit")
    if args.records <= 0 or args.tenants <= 0 or args.restart_every <= 0:
        parser.error("records, tenants, and restart-every must be positive")
    if args.records % args.tenants:
        parser.error("records must be divisible by tenants")
    if args.lifecycle_records <= 0 or args.lifecycle_records * 2 >= args.records:
        parser.error("lifecycle-records must be positive and leave ordinary records")
    return args


def main() -> int:
    args = parse_args()
    if args.prepare_only:
        if PREPARED.exists():
            raise FileExistsError(f"refusing to overwrite {PREPARED}")
        payload = prepared_payload(args)
        write_json(PREPARED, payload, exclusive=True)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    try:
        result = execute(args)
    except Exception as exc:
        result = {
            "schema_version": 1,
            "benchmark": "million_write_sqlite_evidence_store_reliability",
            "status": "ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "created_at": utc_now(),
            "preregistered_commit": args.preregistered_commit,
            "command": [sys.executable, *sys.argv],
        }
        if not RESULT.exists():
            write_json(RESULT, result, exclusive=True)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    write_json(RESULT, result, exclusive=True)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
