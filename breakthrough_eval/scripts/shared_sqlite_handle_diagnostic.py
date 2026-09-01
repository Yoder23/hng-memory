#!/usr/bin/env python3
"""Preregistered matrix isolating shared-SQLite child handle growth."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import shutil
import signal
import statistics
import sys
import time
import traceback
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PACKAGE))

from breakthrough_eval.scripts import handle_observer_diagnostic as observer  # noqa: E402
from breakthrough_eval.scripts import sustained_reliability as sustained  # noqa: E402


SQLiteEvidenceStore = sustained.SQLiteEvidenceStore
OUTPUT_DIR = (
    ROOT / "breakthrough_eval" / "reliability" /
    "shared_sqlite_handle_diagnostic"
)
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
RUN_DATA = OUTPUT_DIR / "run_data"
WRAPPER = Path(__file__).resolve()
STORAGE = PACKAGE / "hngfrontier" / "storage_v2.py"
V2_FAILURE = (
    ROOT / "breakthrough_eval" / "reliability" / "sustained_2h_v2" /
    "FAILURE_ANALYSIS.json"
)
OBSERVER_RESULT = (
    ROOT / "breakthrough_eval" / "reliability" /
    "handle_observer_diagnostic_v3" / "RESULTS.json"
)
SOURCE_FILES = (PROTOCOL, WRAPPER, STORAGE, V2_FAILURE, OBSERVER_RESULT)
CONDITIONS = (
    "idle_12", "isolated_sqlite_12",
    "shared_sqlite_12_a", "shared_sqlite_12_b",
)


def display_path(path: Path) -> str:
    return observer.display_path(path)


def source_hashes() -> dict[str, str]:
    return {display_path(path): observer.sha256_file(path) for path in SOURCE_FILES}


def frozen_config(args: argparse.Namespace) -> dict[str, object]:
    return {
        "conditions": list(CONDITIONS),
        "condition_seconds": args.condition_seconds,
        "sample_interval_seconds": args.sample_interval_seconds,
        "writer_workers": args.writer_workers,
        "reader_workers": args.reader_workers,
        "seed_records": args.seed_records,
        "tenants": args.tenants,
        "minimum_samples_per_child": args.minimum_samples_per_child,
        "shared_support_slope_handles_per_minute": (
            args.shared_support_slope_handles_per_minute
        ),
        "shared_replication_tolerance_handles_per_minute": (
            args.shared_replication_tolerance_handles_per_minute
        ),
        "control_maximum_slope_handles_per_minute": (
            args.control_maximum_slope_handles_per_minute
        ),
        "process_count_support_slope_handles_per_minute": (
            args.process_count_support_slope_handles_per_minute
        ),
        "multiprocessing_start_method": "spawn",
    }


def prepared_payload(args: argparse.Namespace) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "PREPARED_NOT_EXECUTED",
        "created_at": sustained.utc_now(),
        "config": frozen_config(args),
        "source_sha256": source_hashes(),
        "predecessor_failure": display_path(V2_FAILURE),
        "observer_control": display_path(OBSERVER_RESULT),
        "qualifying_command": [
            sys.executable, display_path(WRAPPER),
            "--preregistered-commit", "COMMIT",
        ],
        "claim_boundary": (
            "Root-cause diagnostic only. It cannot qualify HNG, storage, "
            "recovery, production reliability, or the failed sustained run."
        ),
    }


def verify_prepared(
    payload: Mapping[str, Any], args: argparse.Namespace,
) -> None:
    if payload.get("status") != "PREPARED_NOT_EXECUTED":
        raise RuntimeError("prepared status mismatch")
    if payload.get("config") != frozen_config(args):
        raise RuntimeError("prepared configuration mismatch")
    if payload.get("source_sha256") != source_hashes():
        raise RuntimeError("preregistered source hash mismatch")


def seed_database(path: Path, records: int, tenants: int) -> None:
    store = SQLiteEvidenceStore(path)
    try:
        for index in range(records):
            store.append(sustained.base_record(index, tenants))
    finally:
        store.close()


def prepare_condition_databases(
    condition_dir: Path,
    condition: str,
    workers: int,
    seed_records: int,
    tenants: int,
) -> list[str | None]:
    if condition == "idle_12":
        return [None] * workers
    template = condition_dir / "template.sqlite"
    seed_database(template, seed_records, tenants)
    if condition == "isolated_sqlite_12":
        paths = []
        for index in range(workers):
            target = condition_dir / f"worker-{index:02d}.sqlite"
            shutil.copy2(template, target)
            paths.append(str(target))
        return paths
    shared = condition_dir / "shared.sqlite"
    shutil.copy2(template, shared)
    return [str(shared)] * workers


def matrix_worker(
    condition: str,
    role: str,
    worker_index: int,
    database: str | None,
    condition_epoch: int,
    args_payload: Mapping[str, Any],
    start_ns: Any,
    start_event: Any,
    stop_event: Any,
    ready_event: Any,
    output: Any,
    log_path: str,
) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    store: Any = None
    samples = operations = missing = malformed = 0
    try:
        if sustained.psutil is None or not hasattr(
            sustained.psutil.Process(), "num_handles"
        ):
            raise RuntimeError("Windows psutil num_handles is required")
        if database is not None:
            store = SQLiteEvidenceStore(database)
        process = sustained.psutil.Process(os.getpid())
        ready_event.set()
        if not start_event.wait(timeout=60.0):
            raise TimeoutError("condition start timed out")
        interval = float(args_payload["sample_interval_seconds"])
        tenants = int(args_payload["tenants"])
        seed_records = int(args_payload["seed_records"])
        next_sample = time.monotonic()
        with Path(log_path).open("x", encoding="utf-8", newline="\n") as log:
            while not stop_event.is_set():
                now = time.monotonic()
                if now >= next_sample:
                    wall_ns = time.time_ns()
                    observer.append_fsynced(log, {
                        "condition": condition,
                        "created_at_ns": wall_ns,
                        "elapsed_seconds": (
                            wall_ns - int(start_ns.value)
                        ) / 1_000_000_000,
                        "handles": process.num_handles(),
                        "operations": operations,
                        "pid": os.getpid(),
                        "role": role,
                        "rss_bytes": process.memory_info().rss,
                        "threads": process.num_threads(),
                        "worker_index": worker_index,
                    })
                    samples += 1
                    while next_sample <= now:
                        next_sample += interval
                if condition == "idle_12":
                    stop_event.wait(0.01)
                    continue
                if role == "writer":
                    store.append(sustained.worker_record(
                        condition_epoch, worker_index, operations, tenants
                    ))
                    operations += 1
                else:
                    seed_index = (
                        operations * 17 + worker_index * 13
                        + condition_epoch * 7
                    ) % seed_records
                    identifier = f"probe-{seed_index:08d}"
                    tenant = f"tenant-{seed_index % tenants:03d}"
                    item = store.get(identifier)
                    eligible = store.eligible_ids(
                        tenant_id=tenant,
                        scopes=("tenant",),
                        include_inactive=True,
                    )
                    if item is None or identifier not in eligible:
                        missing += 1
                    elif (
                        item.tenant_id != tenant
                        or item.experience_id != identifier
                    ):
                        malformed += 1
                    operations += 1
        output.put({
            "condition": condition,
            "role": role,
            "worker_index": worker_index,
            "pid": os.getpid(),
            "samples": samples,
            "operations": operations,
            "missing": missing,
            "malformed": malformed,
            "error": None,
        })
    except BaseException as exc:
        output.put({
            "condition": condition,
            "role": role,
            "worker_index": worker_index,
            "pid": os.getpid(),
            "samples": samples,
            "operations": operations,
            "missing": missing,
            "malformed": malformed,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        })
        raise
    finally:
        if store is not None:
            store.close()


def handle_stats(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    elapsed = float(samples[-1]["elapsed_seconds"]) - float(
        samples[0]["elapsed_seconds"]
    )
    net = int(samples[-1]["handles"]) - int(samples[0]["handles"])
    return {
        "samples": len(samples),
        "elapsed_seconds": elapsed,
        "first_handles": int(samples[0]["handles"]),
        "last_handles": int(samples[-1]["handles"]),
        "maximum_handles": max(int(item["handles"]) for item in samples),
        "net_handles": net,
        "slope_handles_per_minute": net / (elapsed / 60.0),
    }


def run_condition(
    context: Any,
    condition: str,
    condition_epoch: int,
    args: argparse.Namespace,
    events: Any,
) -> dict[str, Any]:
    condition_dir = RUN_DATA / condition
    condition_dir.mkdir(parents=True, exist_ok=False)
    workers = args.writer_workers + args.reader_workers
    databases = prepare_condition_databases(
        condition_dir, condition, workers, args.seed_records, args.tenants
    )
    start_ns = context.Value("q", 0)
    start_event = context.Event()
    stop_event = context.Event()
    ready = [context.Event() for _ in range(workers)]
    output = context.Queue()
    payload = frozen_config(args)
    roles = ["writer"] * args.writer_workers + [
        "reader"
    ] * args.reader_workers
    processes = [
        context.Process(
            target=matrix_worker,
            args=(
                condition, roles[index], index, databases[index],
                condition_epoch, payload, start_ns, start_event, stop_event,
                ready[index], output,
                str(condition_dir / f"worker-{index:02d}.jsonl"),
            ),
            name=f"shared-handle-{condition}-{index:02d}",
        )
        for index in range(workers)
    ]
    for process in processes:
        process.start()
    ready_deadline = time.monotonic() + 90.0
    while not all(item.is_set() for item in ready):
        if any(process.exitcode is not None for process in processes):
            raise RuntimeError("child exited before condition readiness")
        if time.monotonic() >= ready_deadline:
            raise TimeoutError("condition readiness timed out")
        time.sleep(0.05)
    start_ns.value = time.time_ns()
    observer.append_fsynced(events, {
        "condition": condition,
        "created_at": sustained.utc_now(),
        "event": "condition_started",
        "pids": [process.pid for process in processes],
    })
    start_event.set()
    deadline = time.monotonic() + args.condition_seconds
    try:
        while time.monotonic() < deadline:
            failures = [
                process for process in processes
                if process.exitcode is not None
            ]
            if failures:
                raise RuntimeError(
                    f"child exited early: "
                    f"{[(item.pid, item.exitcode) for item in failures]}"
                )
            time.sleep(0.05)
    finally:
        stop_event.set()
        for process in processes:
            process.join(timeout=60.0)
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10.0)
    reports = []
    for _ in processes:
        try:
            reports.append(output.get(timeout=5.0))
        except queue.Empty:
            break
    exitcodes = [process.exitcode for process in processes]
    per_child = []
    artifacts = {}
    for index, role in enumerate(roles):
        path = condition_dir / f"worker-{index:02d}.jsonl"
        samples = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        stats = handle_stats(samples)
        per_child.append({
            "worker_index": index, "role": role, **stats,
        })
        artifacts[display_path(path)] = {
            "bytes": path.stat().st_size,
            "sha256": observer.sha256_file(path),
        }
    slopes = [float(item["slope_handles_per_minute"]) for item in per_child]
    validity = {
        "all_children_reported": len(reports) == workers,
        "all_child_exitcodes_zero": all(code == 0 for code in exitcodes),
        "no_child_errors": all(report.get("error") is None for report in reports),
        "minimum_samples_each_child": all(
            int(item["samples"]) >= args.minimum_samples_per_child
            for item in per_child
        ),
        "no_reader_misses": all(
            int(report.get("missing", 0)) == 0
            and int(report.get("malformed", 0)) == 0
            for report in reports
            if report.get("role") == "reader"
        ),
    }
    result = {
        "condition": condition,
        "validity": validity,
        "valid": all(validity.values()),
        "median_slope_handles_per_minute": statistics.median(slopes),
        "minimum_slope_handles_per_minute": min(slopes),
        "maximum_slope_handles_per_minute": max(slopes),
        "per_child": per_child,
        "reports": reports,
        "exitcodes": exitcodes,
        "artifacts": artifacts,
    }
    observer.append_fsynced(events, {
        "condition": condition,
        "created_at": sustained.utc_now(),
        "event": "condition_completed",
        "median_slope_handles_per_minute": result[
            "median_slope_handles_per_minute"
        ],
        "valid": result["valid"],
    })
    for process in processes:
        process.close()
    output.close()
    output.join_thread()
    return result


def classify(
    results: Mapping[str, Mapping[str, Any]], args: argparse.Namespace,
) -> str:
    if not all(bool(item["valid"]) for item in results.values()):
        return "INVALID"
    slopes = {
        name: float(item["median_slope_handles_per_minute"])
        for name, item in results.items()
    }
    if slopes["idle_12"] >= args.process_count_support_slope_handles_per_minute:
        return "SUPPORTS_PROCESS_COUNT_CAUSE"
    shared_a = slopes["shared_sqlite_12_a"]
    shared_b = slopes["shared_sqlite_12_b"]
    if (
        shared_a >= args.shared_support_slope_handles_per_minute
        and shared_b >= args.shared_support_slope_handles_per_minute
        and abs(shared_a - shared_b)
        <= args.shared_replication_tolerance_handles_per_minute
        and slopes["idle_12"] < args.control_maximum_slope_handles_per_minute
        and slopes["isolated_sqlite_12"]
        < args.control_maximum_slope_handles_per_minute
    ):
        return "SUPPORTS_SHARED_SQLITE_CAUSE"
    if all(
        value < args.control_maximum_slope_handles_per_minute
        for value in slopes.values()
    ):
        return "DOES_NOT_REPRODUCE"
    return "INCONCLUSIVE"


def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    if RESULT.exists() or EVENTS.exists() or RUN_DATA.exists():
        raise FileExistsError("matrix targets exist; refusing overwrite/retry")
    RUN_DATA.mkdir(parents=True, exist_ok=False)
    context = mp.get_context("spawn")
    results = {}
    with EVENTS.open("x", encoding="utf-8", newline="\n") as events:
        observer.append_fsynced(events, {
            "created_at": sustained.utc_now(),
            "event": "run_started",
            "config": frozen_config(args),
        })
        for epoch, condition in enumerate(CONDITIONS):
            results[condition] = run_condition(
                context, condition, epoch, args, events
            )
        outcome = classify(results, args)
        observer.append_fsynced(events, {
            "created_at": sustained.utc_now(),
            "event": "run_completed",
            "outcome": outcome,
        })
    valid = all(bool(item["valid"]) for item in results.values())
    return {
        "schema_version": 1,
        "benchmark": "shared_sqlite_child_handle_root_cause_matrix",
        "status": "PASS" if valid else "ERROR",
        "created_at": sustained.utc_now(),
        "config": frozen_config(args),
        "outcome": outcome,
        "conditions": results,
        "events": {
            "path": display_path(EVENTS),
            "bytes": EVENTS.stat().st_size,
            "sha256": observer.sha256_file(EVENTS),
        },
        "claim_boundary": (
            "Root-cause diagnostic only; never HNG, storage, recovery, "
            "production, or sustained-run qualification evidence."
        ),
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    if sustained.psutil is None or not hasattr(
        sustained.psutil.Process(), "num_handles"
    ):
        raise RuntimeError("Windows psutil num_handles is required")
    if not PREPARED.is_file():
        raise FileNotFoundError(PREPARED)
    head = sustained.git("rev-parse", "HEAD")
    if head != args.preregistered_commit:
        raise RuntimeError("HEAD does not match preregistered commit")
    if sustained.git("rev-parse", "origin/main") != head:
        raise RuntimeError("origin/main does not match preregistered HEAD")
    status = sustained.git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise RuntimeError(f"execution requires a clean worktree: {status}")
    payload = json.loads(PREPARED.read_text(encoding="utf-8"))
    verify_prepared(payload, args)
    result = run_matrix(args)
    result.update({
        "preregistered_commit": args.preregistered_commit,
        "protocol": display_path(PROTOCOL),
        "prepared": display_path(PREPARED),
        "command": [sys.executable, *sys.argv],
        "preflight": {
            "clean_worktree": True,
            "origin_main_matches_head": True,
            "source_hashes_match": True,
            "config_matches": True,
        },
    })
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--preregistered-commit")
    parser.add_argument("--condition-seconds", type=float, default=90.0)
    parser.add_argument("--sample-interval-seconds", type=float, default=1.0)
    parser.add_argument("--writer-workers", type=int, default=4)
    parser.add_argument("--reader-workers", type=int, default=8)
    parser.add_argument("--seed-records", type=int, default=1000)
    parser.add_argument("--tenants", type=int, default=100)
    parser.add_argument("--minimum-samples-per-child", type=int, default=80)
    parser.add_argument(
        "--shared-support-slope-handles-per-minute", type=float, default=20.0
    )
    parser.add_argument(
        "--shared-replication-tolerance-handles-per-minute",
        type=float, default=15.0,
    )
    parser.add_argument(
        "--control-maximum-slope-handles-per-minute", type=float, default=5.0
    )
    parser.add_argument(
        "--process-count-support-slope-handles-per-minute",
        type=float, default=20.0,
    )
    args = parser.parse_args()
    if args.prepare_only == bool(args.preregistered_commit):
        parser.error("select exactly one of prepare or execution")
    positive = (
        args.condition_seconds, args.sample_interval_seconds,
        args.writer_workers, args.reader_workers, args.seed_records,
        args.tenants, args.minimum_samples_per_child,
    )
    if any(value <= 0 for value in positive):
        parser.error("durations, intervals, and counts must be positive")
    if args.seed_records % args.tenants:
        parser.error("seed records must be divisible by tenants")
    return args


def main() -> int:
    mp.freeze_support()
    args = parse_args()
    if args.prepare_only:
        if PREPARED.exists():
            raise FileExistsError(f"refusing to overwrite {PREPARED}")
        payload = prepared_payload(args)
        sustained.write_json(PREPARED, payload, exclusive=True)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    try:
        result = execute(args)
    except BaseException as exc:
        result = {
            "schema_version": 1,
            "benchmark": "shared_sqlite_child_handle_root_cause_matrix",
            "status": "ERROR",
            "created_at": sustained.utc_now(),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "preregistered_commit": args.preregistered_commit,
        }
        if not RESULT.exists():
            sustained.write_json(RESULT, result, exclusive=True)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    sustained.write_json(RESULT, result, exclusive=True)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
