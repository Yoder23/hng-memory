"""Preregistered two-hour sustained reliability run with bounded WAL rotation."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import platform
import shutil
import sqlite3
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PACKAGE))

from breakthrough_eval.scripts import sustained_reliability as v1
from breakthrough_eval.scripts import sustained_reliability_v2 as v2


WRAPPER = Path(__file__).resolve()
OUTPUT_DIR = ROOT / "breakthrough_eval" / "reliability" / "sustained_2h_v3"
RUN_DATA = OUTPUT_DIR / "run_data"
DATABASE = RUN_DATA / "sustained-v3.sqlite"
EVENTS = OUTPUT_DIR / "events.jsonl"
RESULT = OUTPUT_DIR / "RESULTS.json"
PREPARED = OUTPUT_DIR / "PREPARED.json"
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
INTERVENTION_RESULT = (
    ROOT / "breakthrough_eval" / "reliability" /
    "wal_checkpoint_rotation_diagnostic" / "RESULTS.json"
)
PREDECESSOR_FAILURE = (
    ROOT / "breakthrough_eval" / "reliability" / "sustained_2h_v2" /
    "FAILURE_ANALYSIS.json"
)
SOURCE_FILES = (
    PROTOCOL,
    WRAPPER,
    Path(v2.__file__).resolve(),
    Path(v1.__file__).resolve(),
    ROOT / "breakthrough_eval" / "scripts" / "storage_reliability_probe.py",
    ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src" /
    "hngfrontier" / "storage_v2.py",
    INTERVENTION_RESULT,
    PREDECESSOR_FAILURE,
)

BASE_RUN_SOAK = v2.run_soak
BASE_STOP_WORKERS = v2.stop_workers
BASE_APPEND_EVENT = v1.append_event
CHECKPOINT_CYCLES: list[dict[str, object]] = []
MAXIMUM_POST_CHECKPOINT_WAL_BYTES = 32_768
MAXIMUM_CHECKPOINT_SECONDS = 30.0


def display_path(path: Path) -> str:
    return v1.display_path(path)


def source_hashes() -> dict[str, str]:
    return {display_path(path): v1.sha256_file(path) for path in SOURCE_FILES}


def frozen_config(args: argparse.Namespace) -> dict[str, object]:
    return {
        "duration_seconds": args.duration_seconds,
        "writer_workers": args.writer_workers,
        "reader_workers": args.reader_workers,
        "tenants": args.tenants,
        "seed_records": args.seed_records,
        "rotation_seconds": args.rotation_seconds,
        "minimum_worker_epochs": args.minimum_worker_epochs,
        "backup_interval_seconds": args.backup_interval_seconds,
        "writer_pause_timeout_seconds": args.writer_pause_timeout_seconds,
        "backup_timeout_seconds": args.backup_timeout_seconds,
        "sample_interval_seconds": args.sample_interval_seconds,
        "minimum_writes": args.minimum_writes,
        "minimum_reads": args.minimum_reads,
        "minimum_backup_cycles": args.minimum_backup_cycles,
        "minimum_resource_samples": args.minimum_resource_samples,
        "maximum_rss_per_process_bytes": args.maximum_rss_per_process_bytes,
        "maximum_handles_per_process": args.maximum_handles_per_process,
        "minimum_free_bytes": args.minimum_free_bytes,
        "runtime_free_floor_bytes": args.runtime_free_floor_bytes,
        "database": display_path(DATABASE),
        "events": display_path(EVENTS),
        "result": display_path(RESULT),
        "journal_mode": "WAL",
        "synchronous": "FULL",
        "multiprocessing_start_method": "spawn",
        "backup_contract": "writers_paused_at_transaction_boundary_readers_live",
        "connection_epoch_contract": "all_workers_replaced_every_30_seconds",
        "checkpoint_contract": "fully_quiescent_truncate_after_every_worker_epoch",
        "maximum_post_checkpoint_wal_bytes": MAXIMUM_POST_CHECKPOINT_WAL_BYTES,
        "maximum_checkpoint_seconds": MAXIMUM_CHECKPOINT_SECONDS,
        "intervention_result": display_path(INTERVENTION_RESULT),
        "predecessor_failure": display_path(PREDECESSOR_FAILURE),
    }


def prepared_payload(args: argparse.Namespace) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "PREPARED_NOT_EXECUTED",
        "created_at": v1.utc_now(),
        "predecessor_failure": display_path(PREDECESSOR_FAILURE),
        "intervention_result": display_path(INTERVENTION_RESULT),
        "hypothesis": (
            "Thirty-second complete connection rotation followed by a fully "
            "quiescent TRUNCATE checkpoint bounds WAL/WAL-index Section-handle "
            "growth below the frozen cap throughout the two-hour v2 recovery "
            "workload without violating exact storage or backup identity."
        ),
        "config": frozen_config(args),
        "source_sha256": source_hashes(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "sqlite": sqlite3.sqlite_version,
            "psutil": None if v1.psutil is None else v1.psutil.__version__,
            "cpu_count": os.cpu_count(),
        },
        "qualifying_command": [
            sys.executable,
            display_path(WRAPPER),
            "--preregistered-commit",
            "COMMIT",
        ],
        "claim_boundary": (
            "Preparation only. V3 tests one two-hour local run with 30-second "
            "connection epochs, fully quiescent checkpoints, and write-quiesced/"
            "read-live backups; it is not crash, power-loss, actual disk-full, "
            "distributed, days-long, leak-absence, or production evidence."
        ),
    }


def verify_prepared(payload: Mapping[str, Any], args: argparse.Namespace) -> None:
    if payload.get("status") != "PREPARED_NOT_EXECUTED":
        raise RuntimeError("prepared status mismatch")
    if payload.get("config") != frozen_config(args):
        raise RuntimeError("prepared configuration mismatch")
    if payload.get("source_sha256") != source_hashes():
        raise RuntimeError("preregistered source hash mismatch")


def sqlite_sidecar_bytes(suffix: str) -> int:
    path = Path(f"{DATABASE}{suffix}")
    return path.stat().st_size if path.exists() else 0


def stop_workers_with_checkpoint(
    processes: Sequence[Any], stop_event: Any, pause_event: Any,
) -> None:
    BASE_STOP_WORKERS(processes, stop_event, pause_event)
    started = time.perf_counter()
    before_wal = sqlite_sidecar_bytes("-wal")
    before_shm = sqlite_sidecar_bytes("-shm")
    connection = sqlite3.connect(DATABASE, timeout=30.0)
    try:
        row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        open_wal = sqlite_sidecar_bytes("-wal")
        open_shm = sqlite_sidecar_bytes("-shm")
    finally:
        connection.close()
    duration = time.perf_counter() - started
    busy, log_frames, checkpointed_frames = (int(value) for value in row)
    post_wal = sqlite_sidecar_bytes("-wal")
    post_shm = sqlite_sidecar_bytes("-shm")
    cycle = {
        "cycle": len(CHECKPOINT_CYCLES) + 1,
        "mode": "TRUNCATE",
        "fully_quiescent": True,
        "duration_seconds": duration,
        "busy": busy,
        "log_frames": log_frames,
        "checkpointed_frames": checkpointed_frames,
        "quick_check": quick_check,
        "before_wal_bytes": before_wal,
        "before_shm_bytes": before_shm,
        "connection_open_wal_bytes": open_wal,
        "connection_open_shm_bytes": open_shm,
        "post_close_wal_bytes": post_wal,
        "post_close_shm_bytes": post_shm,
        "passed": (
            busy == 0
            and quick_check == "ok"
            and post_wal <= MAXIMUM_POST_CHECKPOINT_WAL_BYTES
            and duration <= MAXIMUM_CHECKPOINT_SECONDS
        ),
    }
    CHECKPOINT_CYCLES.append(cycle)
    if not cycle["passed"]:
        raise RuntimeError(f"post-epoch checkpoint failed: {cycle}")


def append_event_with_checkpoint(events: Any, payload: Mapping[str, Any]) -> None:
    enriched = dict(payload)
    if enriched.get("event") == "workers_stopped":
        epoch = int(enriched["epoch"])
        if epoch < len(CHECKPOINT_CYCLES):
            enriched["checkpoint_after_stop"] = CHECKPOINT_CYCLES[epoch]
    BASE_APPEND_EVENT(events, enriched)


def attach_checkpoint_evidence(
    result: dict[str, object], args: argparse.Namespace,
) -> dict[str, object]:
    worker_epochs = list(result["worker_epochs"])
    cycles = list(CHECKPOINT_CYCLES)
    criteria = dict(result["criteria"])
    criteria.update({
        "minimum_checkpoint_cycles_reached": (
            len(cycles) >= args.minimum_worker_epochs
        ),
        "checkpoint_after_every_worker_epoch": (
            len(cycles) == len(worker_epochs)
        ),
        "all_checkpoints_passed": (
            bool(cycles) and all(bool(item["passed"]) for item in cycles)
        ),
        "all_checkpoints_quiescent": (
            bool(cycles)
            and all(bool(item["fully_quiescent"]) for item in cycles)
        ),
        "all_checkpoint_wals_bounded": (
            bool(cycles)
            and all(
                int(item["post_close_wal_bytes"])
                <= MAXIMUM_POST_CHECKPOINT_WAL_BYTES
                for item in cycles
            )
        ),
        "all_checkpoints_in_time": (
            bool(cycles)
            and all(
                float(item["duration_seconds"])
                <= MAXIMUM_CHECKPOINT_SECONDS
                for item in cycles
            )
        ),
    })
    result.update({
        "benchmark": "sustained_2h_v3_checkpoint_bounded_recovery",
        "status": "PASS" if all(criteria.values()) else "FAIL",
        "predecessor_failure": display_path(PREDECESSOR_FAILURE),
        "intervention_result": display_path(INTERVENTION_RESULT),
        "claim_boundary": (
            "One two-hour local write-quiesced/read-live recovery run with "
            "30-second complete connection rotation and fully quiescent "
            "TRUNCATE checkpoints. Not uninterrupted-write backup, crash, "
            "power-loss, actual disk-full, distributed, days-long, leak-absence, "
            "or production evidence."
        ),
        "config": frozen_config(args),
        "criteria": criteria,
        "checkpoint_cycles": cycles,
    })
    return result


def run_soak(args: argparse.Namespace) -> dict[str, object]:
    CHECKPOINT_CYCLES.clear()
    path_names = ("OUTPUT_DIR", "RUN_DATA", "DATABASE", "EVENTS", "RESULT")
    original_paths = {name: getattr(v2, name) for name in path_names}
    original_stop = v2.stop_workers
    original_config = v2.frozen_config
    original_append = v1.append_event
    replacements = {
        "OUTPUT_DIR": OUTPUT_DIR,
        "RUN_DATA": RUN_DATA,
        "DATABASE": DATABASE,
        "EVENTS": EVENTS,
        "RESULT": RESULT,
    }
    try:
        for name, value in replacements.items():
            setattr(v2, name, value)
        v2.stop_workers = stop_workers_with_checkpoint
        v2.frozen_config = frozen_config
        v1.append_event = append_event_with_checkpoint
        result = BASE_RUN_SOAK(args)
    finally:
        for name, value in original_paths.items():
            setattr(v2, name, value)
        v2.stop_workers = original_stop
        v2.frozen_config = original_config
        v1.append_event = original_append
    return attach_checkpoint_evidence(result, args)


def execute(args: argparse.Namespace) -> dict[str, object]:
    if v1.psutil is None:
        raise RuntimeError("psutil is required for v3 execution")
    if not PREPARED.is_file():
        raise FileNotFoundError(PREPARED)
    if RESULT.exists() or EVENTS.exists() or RUN_DATA.exists():
        raise FileExistsError("refusing overwrite/retry of v3 sustained artifacts")
    head = v1.git("rev-parse", "HEAD")
    if head != args.preregistered_commit:
        raise RuntimeError(
            f"HEAD {head} != preregistered commit {args.preregistered_commit}"
        )
    origin = v1.git("rev-parse", "origin/main")
    if origin != head:
        raise RuntimeError(f"origin/main {origin} != preregistered HEAD {head}")
    status = v1.git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise RuntimeError(f"execution requires a clean worktree: {status}")
    payload = json.loads(PREPARED.read_text(encoding="utf-8"))
    verify_prepared(payload, args)
    free_bytes = shutil.disk_usage(OUTPUT_DIR).free
    if free_bytes < args.minimum_free_bytes:
        raise RuntimeError(
            f"free bytes {free_bytes} below frozen minimum {args.minimum_free_bytes}"
        )
    result = run_soak(args)
    result.update({
        "protocol": display_path(PROTOCOL),
        "prepared": display_path(PREPARED),
        "preregistered_commit": args.preregistered_commit,
        "command": [sys.executable, *sys.argv],
        "preflight": {
            "clean_worktree": True,
            "origin_main_matches_head": True,
            "source_hashes_match": True,
            "config_matches": True,
            "free_bytes_before": free_bytes,
            "minimum_free_bytes": args.minimum_free_bytes,
        },
        "database_file_sha256": v1.sha256_file(DATABASE),
    })
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--preregistered-commit")
    parser.add_argument("--duration-seconds", type=float, default=7200.0)
    parser.add_argument("--writer-workers", type=int, default=4)
    parser.add_argument("--reader-workers", type=int, default=8)
    parser.add_argument("--tenants", type=int, default=100)
    parser.add_argument("--seed-records", type=int, default=1000)
    parser.add_argument("--rotation-seconds", type=float, default=30.0)
    parser.add_argument("--minimum-worker-epochs", type=int, default=216)
    parser.add_argument("--backup-interval-seconds", type=float, default=600.0)
    parser.add_argument("--writer-pause-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--backup-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--sample-interval-seconds", type=float, default=30.0)
    parser.add_argument("--minimum-writes", type=int, default=100_000)
    parser.add_argument("--minimum-reads", type=int, default=100_000)
    parser.add_argument("--minimum-backup-cycles", type=int, default=12)
    parser.add_argument("--minimum-resource-samples", type=int, default=216)
    parser.add_argument("--maximum-rss-per-process-bytes", type=int, default=1_500_000_000)
    parser.add_argument("--maximum-handles-per-process", type=int, default=1024)
    parser.add_argument("--minimum-free-bytes", type=int, default=40_000_000_000)
    parser.add_argument("--runtime-free-floor-bytes", type=int, default=30_000_000_000)
    args = parser.parse_args()
    if args.prepare_only == bool(args.preregistered_commit):
        parser.error("select exactly one of --prepare-only or --preregistered-commit")
    positive = (
        args.duration_seconds, args.writer_workers, args.reader_workers,
        args.tenants, args.seed_records, args.rotation_seconds,
        args.minimum_worker_epochs, args.backup_interval_seconds,
        args.writer_pause_timeout_seconds, args.backup_timeout_seconds,
        args.sample_interval_seconds, args.minimum_backup_cycles,
        args.minimum_resource_samples,
    )
    if any(value <= 0 for value in positive):
        parser.error("all duration, count, worker, and interval values must be positive")
    if args.seed_records < args.tenants or args.seed_records % args.tenants:
        parser.error("seed-records must be at least and divisible by tenants")
    if args.runtime_free_floor_bytes >= args.minimum_free_bytes:
        parser.error("runtime free floor must be below preflight free minimum")
    return args


def main() -> int:
    mp.freeze_support()
    args = parse_args()
    if args.prepare_only:
        if PREPARED.exists():
            raise FileExistsError(f"refusing to overwrite {PREPARED}")
        payload = prepared_payload(args)
        v1.write_json(PREPARED, payload, exclusive=True)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    try:
        result = execute(args)
    except BaseException as exc:
        result = {
            "schema_version": 1,
            "benchmark": "sustained_2h_v3_checkpoint_bounded_recovery",
            "status": "ERROR",
            "created_at": v1.utc_now(),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "preregistered_commit": args.preregistered_commit,
            "command": [sys.executable, *sys.argv],
            "partial_events": display_path(EVENTS) if EVENTS.exists() else None,
            "completed_checkpoint_cycles": list(CHECKPOINT_CYCLES),
        }
        if not RESULT.exists():
            v1.write_json(RESULT, result, exclusive=True)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    v1.write_json(RESULT, result, exclusive=True)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
