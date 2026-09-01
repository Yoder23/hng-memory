#!/usr/bin/env python3
"""Fail-closed preregistered sustained SQLiteEvidenceStore reliability run."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import platform
import queue
import shutil
import sqlite3
import statistics
import sys
import time
import traceback
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PACKAGE))

try:  # psutil is an evaluation-only dependency, not a package runtime dependency.
    import psutil  # type: ignore[import-not-found]  # noqa: E402
except ImportError:  # pragma: no cover - exercised by dependency-free clones.
    psutil = None  # type: ignore[assignment]

from breakthrough_eval.scripts.storage_reliability_probe import record as base_record  # noqa: E402
from hngfrontier.storage_v2 import SQLiteEvidenceStore  # noqa: E402


OUTPUT_DIR = ROOT / "breakthrough_eval" / "reliability" / "sustained_2h"
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
RUN_DATA = OUTPUT_DIR / "run_data"
DATABASE = RUN_DATA / "sustained.sqlite"
WRAPPER = Path(__file__).resolve()
STORAGE = PACKAGE / "hngfrontier" / "storage_v2.py"
BOUNDED_PROBE = ROOT / "breakthrough_eval" / "scripts" / "storage_reliability_probe.py"
SOURCE_FILES = (PROTOCOL, WRAPPER, STORAGE, BOUNDED_PROBE)
CREATED_AT = "2026-09-01T16:00:00+00:00"
LATENCY_BOUNDS_MS = (
    1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0,
    250.0, 500.0, 1000.0, 5000.0, 30000.0,
)
TABLE_ORDER = (
    ("evidence", "experience_id"),
    ("working_state", "conversation_id"),
    ("deterministic_working_state", "conversation_id"),
    ("meta", "key"),
)


def utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    import subprocess
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return completed.stdout.strip()


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def source_hashes() -> dict[str, str]:
    return {display_path(path): sha256_file(path) for path in SOURCE_FILES}


def frozen_config(args: argparse.Namespace) -> dict[str, object]:
    return {
        "duration_seconds": args.duration_seconds,
        "writer_workers": args.writer_workers,
        "reader_workers": args.reader_workers,
        "tenants": args.tenants,
        "seed_records": args.seed_records,
        "rotation_seconds": args.rotation_seconds,
        "backup_interval_seconds": args.backup_interval_seconds,
        "sample_interval_seconds": args.sample_interval_seconds,
        "minimum_writes": args.minimum_writes,
        "minimum_reads": args.minimum_reads,
        "minimum_backup_cycles": args.minimum_backup_cycles,
        "minimum_resource_samples": args.minimum_resource_samples,
        "maximum_rss_per_process_bytes": args.maximum_rss_per_process_bytes,
        "maximum_handles_per_process": args.maximum_handles_per_process,
        "minimum_free_bytes": args.minimum_free_bytes,
        "database": display_path(DATABASE),
        "events": display_path(EVENTS),
        "result": display_path(RESULT),
        "journal_mode": "WAL",
        "synchronous": "FULL",
        "multiprocessing_start_method": "spawn",
    }


def prepared_payload(args: argparse.Namespace) -> dict[str, object]:
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
            "psutil": None if psutil is None else psutil.__version__,
            "cpu_count": os.cpu_count(),
        },
        "qualifying_command": [
            sys.executable, display_path(WRAPPER),
            "--preregistered-commit", "COMMIT",
        ],
        "claim_boundary": (
            "Preparation only. The intended run is a sustained local multi-process SQLite "
            "probe, not OS-crash, power-loss, actual filesystem exhaustion, or production "
            "deployment evidence."
        ),
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


def append_event(handle: Any, event: Mapping[str, Any]) -> None:
    payload = {"created_at": utc_now(), **dict(event)}
    handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def histogram() -> dict[str, object]:
    return {
        "count": 0, "sum_ms": 0.0, "maximum_ms": 0.0,
        "buckets": [0] * (len(LATENCY_BOUNDS_MS) + 1),
    }


def observe(target: dict[str, object], milliseconds: float) -> None:
    target["count"] = int(target["count"]) + 1
    target["sum_ms"] = float(target["sum_ms"]) + milliseconds
    target["maximum_ms"] = max(float(target["maximum_ms"]), milliseconds)
    buckets = target["buckets"]
    assert isinstance(buckets, list)
    index = len(LATENCY_BOUNDS_MS)
    for candidate, bound in enumerate(LATENCY_BOUNDS_MS):
        if milliseconds <= bound:
            index = candidate
            break
    buckets[index] = int(buckets[index]) + 1


def merge_histograms(values: Iterable[Mapping[str, object]]) -> dict[str, object]:
    merged = histogram()
    buckets = merged["buckets"]
    assert isinstance(buckets, list)
    for value in values:
        merged["count"] = int(merged["count"]) + int(value["count"])
        merged["sum_ms"] = float(merged["sum_ms"]) + float(value["sum_ms"])
        merged["maximum_ms"] = max(
            float(merged["maximum_ms"]), float(value["maximum_ms"])
        )
        for index, count in enumerate(value["buckets"]):
            buckets[index] = int(buckets[index]) + int(count)
    return merged


def histogram_summary(value: Mapping[str, object]) -> dict[str, object]:
    count = int(value["count"])
    buckets = [int(item) for item in value["buckets"]]

    def upper_quantile(fraction: float) -> float | str | None:
        if count == 0:
            return None
        target = math.ceil(count * fraction)
        cumulative = 0
        for index, bucket_count in enumerate(buckets):
            cumulative += bucket_count
            if cumulative >= target:
                return (
                    LATENCY_BOUNDS_MS[index]
                    if index < len(LATENCY_BOUNDS_MS)
                    else ">30000"
                )
        raise AssertionError("histogram count mismatch")

    return {
        "count": count,
        "mean_ms": None if count == 0 else float(value["sum_ms"]) / count,
        "maximum_ms": float(value["maximum_ms"]),
        "p50_upper_bound_ms": upper_quantile(0.50),
        "p95_upper_bound_ms": upper_quantile(0.95),
        "p99_upper_bound_ms": upper_quantile(0.99),
        "bucket_upper_bounds_ms": [*LATENCY_BOUNDS_MS, ">30000"],
        "bucket_counts": buckets,
    }


def worker_record(epoch: int, worker: int, counter: int, tenants: int) -> Any:
    ordinal = (
        10_000_000_000 + epoch * 1_000_000_000
        + worker * 100_000_000 + counter
    )
    identifier = f"soak-e{epoch:03d}-w{worker:02d}-{counter:09d}"
    item = base_record(ordinal, tenants)
    return replace(
        item,
        experience_id=identifier,
        evidence_group_id=f"event-{identifier}",
        source_event_id=f"event-{identifier}",
        episode_id=f"episode-e{epoch:03d}-w{worker:02d}-{counter // 10:08d}",
        conversation_id=(
            f"conversation-e{epoch:03d}-w{worker:02d}-{counter // 100:08d}"
        ),
        content=(
            f"sustained reliability observation epoch={epoch} "
            f"worker={worker} counter={counter}"
        ),
        metadata={
            "probe": "sustained_2h", "epoch": epoch,
            "worker": worker, "counter": counter,
        },
        created_at=CREATED_AT,
    )


def writer_worker(
    database: str, epoch: int, worker: int, tenants: int,
    stop_event: Any, output: Any,
) -> None:
    stats = histogram()
    completed = 0
    store: SQLiteEvidenceStore | None = None
    try:
        store = SQLiteEvidenceStore(database)
        while not stop_event.is_set():
            started = time.perf_counter()
            store.append(worker_record(epoch, worker, completed, tenants))
            observe(stats, (time.perf_counter() - started) * 1000.0)
            completed += 1
        output.put({
            "kind": "writer", "epoch": epoch, "worker": worker,
            "completed": completed, "latency": stats, "error": None,
        })
    except BaseException as exc:
        output.put({
            "kind": "writer", "epoch": epoch, "worker": worker,
            "completed": completed, "latency": stats,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        })
        raise
    finally:
        if store is not None:
            store.close()


def reader_worker(
    database: str, epoch: int, worker: int, tenants: int, seed_records: int,
    stop_event: Any, output: Any,
) -> None:
    stats = histogram()
    checks = missing = malformed = 0
    store: SQLiteEvidenceStore | None = None
    try:
        store = SQLiteEvidenceStore(database)
        while not stop_event.is_set():
            seed_index = (checks * 17 + worker * 13 + epoch * 7) % seed_records
            identifier = f"probe-{seed_index:08d}"
            tenant = f"tenant-{seed_index % tenants:03d}"
            started = time.perf_counter()
            item = store.get(identifier)
            eligible = store.eligible_ids(
                tenant_id=tenant, scopes=("tenant",), include_inactive=True,
            )
            observe(stats, (time.perf_counter() - started) * 1000.0)
            if item is None or identifier not in eligible:
                missing += 1
            elif item.tenant_id != tenant or item.experience_id != identifier:
                malformed += 1
            checks += 1
        output.put({
            "kind": "reader", "epoch": epoch, "worker": worker,
            "checks": checks, "missing": missing, "malformed": malformed,
            "latency": stats, "error": None,
        })
    except BaseException as exc:
        output.put({
            "kind": "reader", "epoch": epoch, "worker": worker,
            "checks": checks, "missing": missing, "malformed": malformed,
            "latency": stats, "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        })
        raise
    finally:
        if store is not None:
            store.close()


def logical_digest(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    connection = sqlite3.connect(
        f"file:{path.resolve().as_posix()}?mode=ro", uri=True
    )
    evidence_count = 0
    try:
        for table, order_by in TABLE_ORDER:
            columns = [
                str(row[1])
                for row in connection.execute(f"PRAGMA table_info({table})")
            ]
            digest.update(json.dumps(
                {"table": table, "columns": columns},
                separators=(",", ":"),
            ).encode())
            table_count = 0
            for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY {order_by}"
            ):
                digest.update(json.dumps(
                    row, separators=(",", ":"), ensure_ascii=False,
                ).encode("utf-8"))
                digest.update(b"\n")
                table_count += 1
            if table == "evidence":
                evidence_count = table_count
        generation_row = connection.execute(
            "SELECT value FROM meta WHERE key='evidence_generation'"
        ).fetchone()
        generation = -1 if generation_row is None else int(generation_row[0])
    finally:
        connection.close()
    return {
        "evidence_count": evidence_count,
        "generation": generation,
        "sha256": digest.hexdigest(),
    }


def remove_sqlite_temporary(path: Path) -> None:
    for candidate in (
        path, Path(str(path) + "-wal"), Path(str(path) + "-shm"),
    ):
        if candidate.exists():
            candidate.unlink()


def backup_restore_cycle(
    live_store: SQLiteEvidenceStore,
    cycle: int,
    *,
    expected_live: Mapping[str, object] | None = None,
) -> dict[str, object]:
    backup = RUN_DATA / f"backup-{cycle:02d}.sqlite"
    restored_path = RUN_DATA / f"restore-{cycle:02d}.sqlite"
    if backup.exists() or restored_path.exists():
        raise FileExistsError(
            f"backup cycle target already exists: {backup} or {restored_path}"
        )
    started = time.perf_counter()
    destination = sqlite3.connect(backup)
    try:
        live_store.snapshot().backup(destination, pages=4096, sleep=0.05)
    finally:
        destination.close()
    backup_digest = logical_digest(backup)

    source = sqlite3.connect(
        f"file:{backup.resolve().as_posix()}?mode=ro", uri=True
    )
    restored = sqlite3.connect(restored_path)
    try:
        source.backup(restored, pages=4096, sleep=0.05)
    finally:
        restored.close()
        source.close()
    restored_digest = logical_digest(restored_path)
    restored_store = SQLiteEvidenceStore(restored_path)
    try:
        sentinel_present = restored_store.get("probe-00000000") is not None
        restored_generation = restored_store.generation()
    finally:
        restored_store.close()

    result = {
        "cycle": cycle,
        "duration_seconds": time.perf_counter() - started,
        "backup": display_path(backup),
        "backup_bytes": backup.stat().st_size,
        "backup_file_sha256": sha256_file(backup),
        "restored_bytes": restored_path.stat().st_size,
        "restored_file_sha256": sha256_file(restored_path),
        "backup_logical": backup_digest,
        "restored_logical": restored_digest,
        "sentinel_present": sentinel_present,
        "restored_generation": restored_generation,
    }
    result["logical_identity"] = backup_digest == restored_digest
    result["expected_live_identity"] = (
        None if expected_live is None else backup_digest == expected_live
    )
    result["passed"] = bool(
        result["logical_identity"]
        and sentinel_present
        and restored_generation == backup_digest["generation"]
        and (expected_live is None or result["expected_live_identity"])
    )
    remove_sqlite_temporary(restored_path)
    return result


def resource_sample(
    processes: Sequence[Any], started: float,
) -> dict[str, object]:
    if psutil is None:
        raise RuntimeError("psutil is required for resource sampling")
    pids = [
        os.getpid(),
        *[process.pid for process in processes if process.pid is not None],
    ]
    rows = []
    for pid in pids:
        try:
            process = psutil.Process(pid)
            rows.append({
                "pid": pid,
                "rss_bytes": process.memory_info().rss,
                "handles": (
                    process.num_handles()
                    if hasattr(process, "num_handles") else None
                ),
                "threads": process.num_threads(),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            rows.append({"pid": pid, "unavailable": True})
    available = [row for row in rows if "rss_bytes" in row]
    wal = Path(str(DATABASE) + "-wal")
    return {
        "elapsed_seconds": time.perf_counter() - started,
        "processes": rows,
        "process_count": len(available),
        "total_rss_bytes": sum(int(row["rss_bytes"]) for row in available),
        "maximum_process_rss_bytes": max(
            (int(row["rss_bytes"]) for row in available), default=0,
        ),
        "maximum_process_handles": max(
            (
                int(row["handles"])
                for row in available
                if row.get("handles") is not None
            ),
            default=0,
        ),
        "database_bytes": DATABASE.stat().st_size if DATABASE.exists() else 0,
        "wal_bytes": wal.stat().st_size if wal.exists() else 0,
    }


def stop_workers(processes: Sequence[Any], stop_event: Any) -> None:
    stop_event.set()
    for process in processes:
        process.join(timeout=60.0)
    alive = [process for process in processes if process.is_alive()]
    if alive:
        for process in alive:
            process.terminate()
        for process in alive:
            process.join(timeout=30.0)
        raise RuntimeError(
            f"workers failed to stop cleanly: {[process.pid for process in alive]}"
        )


def collect_reports(
    output: Any, expected: int,
) -> list[dict[str, object]]:
    reports = []
    deadline = time.monotonic() + 30.0
    while len(reports) < expected:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            reports.append(output.get(timeout=remaining))
        except queue.Empty:
            break
    return reports


def start_workers(
    context: Any,
    output: Any,
    stop_event: Any,
    epoch: int,
    args: argparse.Namespace,
) -> list[Any]:
    processes = []
    for worker in range(args.writer_workers):
        processes.append(context.Process(
            target=writer_worker,
            args=(
                str(DATABASE), epoch, worker, args.tenants,
                stop_event, output,
            ),
            name=f"hng-writer-e{epoch}-w{worker}",
        ))
    for worker in range(args.reader_workers):
        processes.append(context.Process(
            target=reader_worker,
            args=(
                str(DATABASE), epoch, worker, args.tenants,
                args.seed_records, stop_event, output,
            ),
            name=f"hng-reader-e{epoch}-r{worker}",
        ))
    for process in processes:
        process.start()
    return processes


def run_soak(args: argparse.Namespace) -> dict[str, object]:
    if DATABASE.exists() or EVENTS.exists() or RESULT.exists() or RUN_DATA.exists():
        raise FileExistsError(
            "sustained run targets already exist; refusing overwrite or retry"
        )
    RUN_DATA.mkdir(parents=True, exist_ok=False)
    seed_store = SQLiteEvidenceStore(DATABASE)
    for index in range(args.seed_records):
        seed_store.append(base_record(index, args.tenants))
    seed_store.close()

    context = mp.get_context("spawn")
    all_reports: list[dict[str, object]] = []
    backup_cycles: list[dict[str, object]] = []
    resource_samples: list[dict[str, object]] = []
    worker_epochs: list[dict[str, object]] = []
    active: list[Any] = []
    active_stop: Any = None
    started = time.perf_counter()
    deadline = started + args.duration_seconds
    next_backup = started + args.backup_interval_seconds
    next_sample = started
    epoch = 0
    live_store = SQLiteEvidenceStore(DATABASE)
    try:
        with EVENTS.open("x", encoding="utf-8", newline="\n") as events:
            append_event(
                events, {"event": "run_started", "config": frozen_config(args)}
            )
            while time.perf_counter() < deadline:
                active_stop = context.Event()
                output = context.Queue()
                active = start_workers(
                    context, output, active_stop, epoch, args
                )
                epoch_started = time.perf_counter()
                epoch_deadline = min(
                    deadline, epoch_started + args.rotation_seconds
                )
                append_event(events, {
                    "event": "workers_started",
                    "epoch": epoch,
                    "pids": [process.pid for process in active],
                })
                while time.perf_counter() < epoch_deadline:
                    failed = [
                        {
                            "pid": process.pid,
                            "name": process.name,
                            "exitcode": process.exitcode,
                        }
                        for process in active
                        if process.exitcode is not None
                    ]
                    if failed:
                        raise RuntimeError(
                            f"worker exited before rotation: {failed}"
                        )
                    now = time.perf_counter()
                    if now >= next_sample:
                        sample = resource_sample(active, started)
                        resource_samples.append(sample)
                        append_event(
                            events, {"event": "resource_sample", **sample}
                        )
                        next_sample += args.sample_interval_seconds
                    if now >= next_backup:
                        cycle = backup_restore_cycle(
                            live_store, len(backup_cycles) + 1
                        )
                        backup_cycles.append(cycle)
                        append_event(
                            events, {"event": "backup_restore", **cycle}
                        )
                        next_backup += args.backup_interval_seconds
                    time.sleep(0.05)

                stop_workers(active, active_stop)
                reports = collect_reports(output, len(active))
                epoch_result = {
                    "epoch": epoch,
                    "duration_seconds": time.perf_counter() - epoch_started,
                    "worker_count": len(active),
                    "reports_received": len(reports),
                    "exitcodes": [
                        process.exitcode for process in active
                    ],
                    "passed": (
                        len(reports) == len(active)
                        and all(process.exitcode == 0 for process in active)
                        and all(
                            report.get("error") is None
                            for report in reports
                        )
                    ),
                }
                worker_epochs.append(epoch_result)
                all_reports.extend(reports)
                append_event(events, {
                    "event": "workers_stopped",
                    **epoch_result,
                    "reports": reports,
                })
                active = []
                active_stop = None
                epoch += 1

            concurrent_duration = time.perf_counter() - started
            final_live = logical_digest(DATABASE)
            final_cycle = backup_restore_cycle(
                live_store,
                len(backup_cycles) + 1,
                expected_live=final_live,
            )
            backup_cycles.append(final_cycle)
            append_event(
                events, {"event": "final_backup_restore", **final_cycle}
            )
    except BaseException:
        if active and active_stop is not None:
            try:
                stop_workers(active, active_stop)
            except Exception:
                pass
        raise
    finally:
        live_store.close()

    writers = [
        report for report in all_reports
        if report.get("kind") == "writer"
    ]
    readers = [
        report for report in all_reports
        if report.get("kind") == "reader"
    ]
    writes = sum(int(report["completed"]) for report in writers)
    reads = sum(int(report["checks"]) for report in readers)
    missing_reads = sum(int(report["missing"]) for report in readers)
    malformed_reads = sum(int(report["malformed"]) for report in readers)
    worker_errors = [
        report for report in all_reports if report.get("error")
    ]
    writer_latency = histogram_summary(merge_histograms(
        report["latency"] for report in writers
    ))
    reader_latency = histogram_summary(merge_histograms(
        report["latency"] for report in readers
    ))
    max_rss = max(
        (
            int(sample["maximum_process_rss_bytes"])
            for sample in resource_samples
        ),
        default=0,
    )
    max_handles = max(
        (
            int(sample["maximum_process_handles"])
            for sample in resource_samples
        ),
        default=0,
    )
    expected_count = args.seed_records + writes
    criteria = {
        "duration_reached": concurrent_duration >= args.duration_seconds,
        "minimum_writes_reached": writes >= args.minimum_writes,
        "minimum_reads_reached": reads >= args.minimum_reads,
        "all_worker_epochs_passed": (
            bool(worker_epochs)
            and all(item["passed"] for item in worker_epochs)
        ),
        "zero_worker_errors": not worker_errors,
        "zero_reader_misses": missing_reads == 0,
        "zero_malformed_reads": malformed_reads == 0,
        "minimum_backup_cycles_reached": (
            len(backup_cycles) >= args.minimum_backup_cycles
        ),
        "all_backup_restore_cycles_passed": all(
            item["passed"] for item in backup_cycles
        ),
        "final_record_count_exact": (
            final_live["evidence_count"] == expected_count
        ),
        "final_generation_exact": (
            final_live["generation"] == expected_count
        ),
        "minimum_resource_samples_reached": (
            len(resource_samples) >= args.minimum_resource_samples
        ),
        "rss_cap_respected": (
            max_rss <= args.maximum_rss_per_process_bytes
        ),
        "handle_cap_respected": (
            max_handles <= args.maximum_handles_per_process
        ),
    }
    passed = all(criteria.values())
    rss_values = [
        int(sample["maximum_process_rss_bytes"])
        for sample in resource_samples
    ]
    handle_values = [
        int(sample["maximum_process_handles"])
        for sample in resource_samples
    ]
    decile = max(1, len(resource_samples) // 10)
    return {
        "schema_version": 1,
        "benchmark": (
            "sustained_2h_multiprocess_sqlite_evidence_store_reliability"
        ),
        "status": "PASS" if passed else "FAIL",
        "claim_boundary": (
            "Sustained local multi-process SQLiteEvidenceStore exercise "
            "with graceful worker rotation and online backup/restore. "
            "Not OS-crash, power-loss, actual disk-full, distributed, or "
            "production-deployment evidence; resource sampling does not "
            "prove absence of leaks."
        ),
        "config": frozen_config(args),
        "concurrent_duration_seconds": concurrent_duration,
        "criteria": criteria,
        "worker_epochs": worker_epochs,
        "workers": {
            "writer_reports": len(writers),
            "reader_reports": len(readers),
            "errors": worker_errors,
        },
        "writes": {
            "completed": writes,
            "latency_ms_histogram": writer_latency,
        },
        "reads": {
            "completed": reads,
            "missing": missing_reads,
            "malformed": malformed_reads,
            "latency_ms_histogram": reader_latency,
        },
        "backup_restore_cycles": backup_cycles,
        "final_live_logical": final_live,
        "expected_final_evidence_count": expected_count,
        "resource_observations": {
            "samples": len(resource_samples),
            "maximum_process_rss_bytes": max_rss,
            "maximum_process_handles": max_handles,
            "rss_first_decile_median": (
                None if not rss_values
                else statistics.median(rss_values[:decile])
            ),
            "rss_last_decile_median": (
                None if not rss_values
                else statistics.median(rss_values[-decile:])
            ),
            "handles_first_decile_median": (
                None if not handle_values
                else statistics.median(handle_values[:decile])
            ),
            "handles_last_decile_median": (
                None if not handle_values
                else statistics.median(handle_values[-decile:])
            ),
            "first_sample": (
                None if not resource_samples else resource_samples[0]
            ),
            "last_sample": (
                None if not resource_samples else resource_samples[-1]
            ),
        },
        "database": display_path(DATABASE),
        "database_bytes": DATABASE.stat().st_size,
        "events": display_path(EVENTS),
    }


def execute(args: argparse.Namespace) -> dict[str, object]:
    if not PREPARED.is_file():
        raise FileNotFoundError(PREPARED)
    if RESULT.exists() or EVENTS.exists() or RUN_DATA.exists():
        raise FileExistsError(
            "refusing overwrite/retry of sustained reliability artifacts"
        )
    if psutil is None:
        raise RuntimeError("psutil is required for sustained execution")
    head = git("rev-parse", "HEAD")
    if head != args.preregistered_commit:
        raise RuntimeError(
            f"HEAD {head} != preregistered commit "
            f"{args.preregistered_commit}"
        )
    status = git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise RuntimeError(
            f"execution requires a clean worktree: {status}"
        )
    payload = json.loads(PREPARED.read_text(encoding="utf-8"))
    verify_prepared(payload, args)
    free_bytes = shutil.disk_usage(OUTPUT_DIR).free
    if free_bytes < args.minimum_free_bytes:
        raise RuntimeError(
            f"free bytes {free_bytes} below frozen minimum "
            f"{args.minimum_free_bytes}"
        )
    result = run_soak(args)
    result.update({
        "protocol": display_path(PROTOCOL),
        "prepared": display_path(PREPARED),
        "preregistered_commit": args.preregistered_commit,
        "command": [sys.executable, *sys.argv],
        "preflight": {
            "clean_worktree": True,
            "source_hashes_match": True,
            "config_matches": True,
            "free_bytes_before": free_bytes,
            "minimum_free_bytes": args.minimum_free_bytes,
        },
        "database_file_sha256": sha256_file(DATABASE),
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
    parser.add_argument("--rotation-seconds", type=float, default=900.0)
    parser.add_argument(
        "--backup-interval-seconds", type=float, default=600.0
    )
    parser.add_argument(
        "--sample-interval-seconds", type=float, default=60.0
    )
    parser.add_argument("--minimum-writes", type=int, default=100_000)
    parser.add_argument("--minimum-reads", type=int, default=100_000)
    parser.add_argument("--minimum-backup-cycles", type=int, default=12)
    parser.add_argument(
        "--minimum-resource-samples", type=int, default=100
    )
    parser.add_argument(
        "--maximum-rss-per-process-bytes",
        type=int,
        default=1_500_000_000,
    )
    parser.add_argument(
        "--maximum-handles-per-process", type=int, default=1024
    )
    parser.add_argument(
        "--minimum-free-bytes", type=int, default=40_000_000_000
    )
    args = parser.parse_args()
    if args.prepare_only == bool(args.preregistered_commit):
        parser.error(
            "select exactly one of --prepare-only or "
            "--preregistered-commit"
        )
    positive = (
        args.duration_seconds,
        args.writer_workers,
        args.reader_workers,
        args.tenants,
        args.seed_records,
        args.rotation_seconds,
        args.backup_interval_seconds,
        args.sample_interval_seconds,
        args.minimum_backup_cycles,
        args.minimum_resource_samples,
    )
    if any(value <= 0 for value in positive):
        parser.error(
            "duration, worker, tenant, seed, interval, and minimum-count "
            "values must be positive"
        )
    if args.seed_records < args.tenants:
        parser.error(
            "seed-records must be at least as large as tenants"
        )
    if args.seed_records % args.tenants:
        parser.error("seed-records must be divisible by tenants")
    return args


def main() -> int:
    mp.freeze_support()
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
    except BaseException as exc:
        result = {
            "schema_version": 1,
            "benchmark": (
                "sustained_2h_multiprocess_"
                "sqlite_evidence_store_reliability"
            ),
            "status": "ERROR",
            "created_at": utc_now(),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "preregistered_commit": args.preregistered_commit,
            "command": [sys.executable, *sys.argv],
            "partial_events": (
                display_path(EVENTS) if EVENTS.exists() else None
            ),
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
