#!/usr/bin/env python3
"""Fail-closed v2 sustained recovery run with monitored backup quiescence."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import multiprocessing as mp
import os
from pathlib import Path
import platform
import queue
import shutil
import signal
import sqlite3
import statistics
import sys
import time
import traceback
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PACKAGE))

from breakthrough_eval.scripts import sustained_reliability as v1  # noqa: E402


SQLiteEvidenceStore = v1.SQLiteEvidenceStore
OUTPUT_DIR = ROOT / "breakthrough_eval" / "reliability" / "sustained_2h_v2"
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
RUN_DATA = OUTPUT_DIR / "run_data"
DATABASE = RUN_DATA / "sustained_v2.sqlite"
WRAPPER = Path(__file__).resolve()
V1_WRAPPER = ROOT / "breakthrough_eval" / "scripts" / "sustained_reliability.py"
STORAGE_PROBE = (
    ROOT / "breakthrough_eval" / "scripts" / "storage_reliability_probe.py"
)
STORAGE = PACKAGE / "hngfrontier" / "storage_v2.py"
SOURCE_FILES = (PROTOCOL, WRAPPER, V1_WRAPPER, STORAGE_PROBE, STORAGE)


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
    }


def prepared_payload(args: argparse.Namespace) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "PREPARED_NOT_EXECUTED",
        "created_at": v1.utc_now(),
        "predecessor_failure": (
            "breakthrough_eval/reliability/sustained_2h/INTERRUPTED.json"
        ),
        "hypothesis": (
            "Bounded write quiescence plus a monitored timeout-bounded backup "
            "child prevents v1 online-backup starvation while scoped readers "
            "remain live."
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
            "Preparation only. V2 tests write-quiesced/read-live recovery, "
            "not uninterrupted-write backup, crash, power-loss, actual "
            "disk-full, or production deployment behavior."
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


def v2_record(
    epoch: int, worker: int, counter: int, tenants: int,
) -> Any:
    item = v1.worker_record(epoch, worker, counter, tenants)
    return replace(
        item,
        metadata={
            **dict(item.metadata),
            "probe": "sustained_2h_v2",
            "recovery_contract": "write_quiesced_read_live",
        },
    )


def writer_worker(
    database: str,
    epoch: int,
    worker: int,
    tenants: int,
    stop_event: Any,
    pause_event: Any,
    paused_ack: Any,
    output: Any,
) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    stats = v1.histogram()
    completed = pause_count = 0
    store: Any = None
    try:
        store = SQLiteEvidenceStore(database)
        while not stop_event.is_set():
            if pause_event.is_set():
                paused_ack.set()
                pause_count += 1
                while pause_event.is_set() and not stop_event.is_set():
                    stop_event.wait(0.05)
                paused_ack.clear()
                continue
            started = time.perf_counter()
            store.append(v2_record(epoch, worker, completed, tenants))
            v1.observe(stats, (time.perf_counter() - started) * 1000.0)
            completed += 1
        output.put({
            "kind": "writer",
            "epoch": epoch,
            "worker": worker,
            "completed": completed,
            "pause_count": pause_count,
            "latency": stats,
            "error": None,
        })
    except BaseException as exc:
        output.put({
            "kind": "writer",
            "epoch": epoch,
            "worker": worker,
            "completed": completed,
            "pause_count": pause_count,
            "latency": stats,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        })
        raise
    finally:
        if store is not None:
            store.close()


def reader_worker(*args: Any) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    v1.reader_worker(*args)


def remove_sqlite_temporary(path: Path) -> None:
    v1.remove_sqlite_temporary(path)


def backup_worker(
    database: str,
    backup: str,
    restored_path: str,
    cycle: int,
    output: Any,
) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    database_path = Path(database)
    backup_path = Path(backup)
    restore_path = Path(restored_path)
    live: Any = None
    try:
        started = time.perf_counter()
        live = SQLiteEvidenceStore(database_path)
        destination = sqlite3.connect(backup_path)
        try:
            live.snapshot().backup(destination, pages=4096, sleep=0.05)
        finally:
            destination.close()
            live.close()
            live = None
        backup_digest = v1.logical_digest(backup_path)
        source = sqlite3.connect(
            f"file:{backup_path.resolve().as_posix()}?mode=ro", uri=True
        )
        restored = sqlite3.connect(restore_path)
        try:
            source.backup(restored, pages=4096, sleep=0.05)
        finally:
            restored.close()
            source.close()
        restored_digest = v1.logical_digest(restore_path)
        restored_store = SQLiteEvidenceStore(restore_path)
        try:
            sentinel_present = (
                restored_store.get("probe-00000000") is not None
            )
            restored_generation = restored_store.generation()
        finally:
            restored_store.close()
        result = {
            "cycle": cycle,
            "duration_seconds": time.perf_counter() - started,
            "backup": display_path(backup_path),
            "backup_bytes": backup_path.stat().st_size,
            "backup_file_sha256": v1.sha256_file(backup_path),
            "restored_bytes": restore_path.stat().st_size,
            "restored_file_sha256": v1.sha256_file(restore_path),
            "backup_logical": backup_digest,
            "restored_logical": restored_digest,
            "sentinel_present": sentinel_present,
            "restored_generation": restored_generation,
            "logical_identity": backup_digest == restored_digest,
        }
        result["passed"] = bool(
            result["logical_identity"]
            and sentinel_present
            and restored_generation == backup_digest["generation"]
        )
        output.put({"result": result, "error": None})
    except BaseException as exc:
        output.put({
            "result": None,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        })
        raise
    finally:
        if live is not None:
            live.close()


def resource_sample(
    processes: Sequence[Any], started: float,
) -> dict[str, object]:
    if v1.psutil is None:
        raise RuntimeError("psutil is required for resource sampling")
    pids = [
        os.getpid(),
        *[process.pid for process in processes if process.pid is not None],
    ]
    rows = []
    for pid in pids:
        try:
            process = v1.psutil.Process(pid)
            rows.append({
                "pid": pid,
                "rss_bytes": process.memory_info().rss,
                "handles": (
                    process.num_handles()
                    if hasattr(process, "num_handles") else None
                ),
                "threads": process.num_threads(),
            })
        except (v1.psutil.NoSuchProcess, v1.psutil.AccessDenied):
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
        "free_bytes": shutil.disk_usage(OUTPUT_DIR).free,
    }


def enforce_runtime_safety(
    sample: Mapping[str, object], args: argparse.Namespace,
) -> None:
    if (
        int(sample["maximum_process_rss_bytes"])
        > args.maximum_rss_per_process_bytes
    ):
        raise RuntimeError("runtime RSS cap exceeded")
    if (
        int(sample["maximum_process_handles"])
        > args.maximum_handles_per_process
    ):
        raise RuntimeError("runtime handle cap exceeded")
    if int(sample["free_bytes"]) < args.runtime_free_floor_bytes:
        raise RuntimeError("runtime free-space floor breached")


def worker_failures(processes: Sequence[Any]) -> list[dict[str, object]]:
    return [
        {
            "pid": process.pid,
            "name": process.name,
            "exitcode": process.exitcode,
        }
        for process in processes
        if process.exitcode is not None
    ]


def start_workers(
    context: Any,
    epoch: int,
    args: argparse.Namespace,
) -> tuple[list[Any], Any, Any, list[Any], Any]:
    stop_event = context.Event()
    pause_event = context.Event()
    paused_acks = [
        context.Event() for _ in range(args.writer_workers)
    ]
    output = context.Queue()
    processes = []
    for worker in range(args.writer_workers):
        processes.append(context.Process(
            target=writer_worker,
            args=(
                str(DATABASE), epoch, worker, args.tenants,
                stop_event, pause_event, paused_acks[worker], output,
            ),
            name=f"hng-v2-writer-e{epoch}-w{worker}",
        ))
    for worker in range(args.reader_workers):
        processes.append(context.Process(
            target=reader_worker,
            args=(
                str(DATABASE), epoch, worker, args.tenants,
                args.seed_records, stop_event, output,
            ),
            name=f"hng-v2-reader-e{epoch}-r{worker}",
        ))
    for process in processes:
        process.start()
    return processes, stop_event, pause_event, paused_acks, output


def stop_workers(
    processes: Sequence[Any],
    stop_event: Any,
    pause_event: Any,
) -> None:
    pause_event.clear()
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
            f"workers failed to stop cleanly: {[item.pid for item in alive]}"
        )


def collect_reports(output: Any, expected: int) -> list[dict[str, object]]:
    return v1.collect_reports(output, expected)


def maybe_sample(
    *,
    processes: Sequence[Any],
    started: float,
    next_sample: float,
    resource_samples: list[dict[str, object]],
    events: Any,
    args: argparse.Namespace,
) -> float:
    now = time.perf_counter()
    if now < next_sample:
        return next_sample
    sample = resource_sample(processes, started)
    resource_samples.append(sample)
    v1.append_event(events, {"event": "resource_sample", **sample})
    enforce_runtime_safety(sample, args)
    while next_sample <= now:
        next_sample += args.sample_interval_seconds
    return next_sample


def monitored_backup_cycle(
    *,
    context: Any,
    cycle: int,
    active: Sequence[Any],
    pause_event: Any,
    paused_acks: Sequence[Any],
    started: float,
    next_sample: float,
    resource_samples: list[dict[str, object]],
    events: Any,
    args: argparse.Namespace,
    expected_live: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], float]:
    backup = RUN_DATA / f"backup-{cycle:02d}.sqlite"
    restored_path = RUN_DATA / f"restore-{cycle:02d}.sqlite"
    if backup.exists() or restored_path.exists():
        raise FileExistsError(
            f"backup cycle target already exists: {backup} or {restored_path}"
        )
    pause_started = time.perf_counter()
    pause_event.set()
    v1.append_event(events, {
        "event": "writer_pause_requested",
        "cycle": cycle,
    })
    ack_deadline = pause_started + args.writer_pause_timeout_seconds
    while not all(item.is_set() for item in paused_acks):
        failures = worker_failures(active)
        if failures:
            raise RuntimeError(
                f"worker exited while pausing for backup: {failures}"
            )
        if time.perf_counter() >= ack_deadline:
            raise TimeoutError("writer pause acknowledgement timed out")
        next_sample = maybe_sample(
            processes=active,
            started=started,
            next_sample=next_sample,
            resource_samples=resource_samples,
            events=events,
            args=args,
        )
        time.sleep(0.05)
    acknowledgement_seconds = time.perf_counter() - pause_started
    v1.append_event(events, {
        "event": "writers_paused",
        "cycle": cycle,
        "acknowledgement_seconds": acknowledgement_seconds,
    })

    output = context.Queue()
    backup_process = context.Process(
        target=backup_worker,
        args=(
            str(DATABASE), str(backup), str(restored_path),
            cycle, output,
        ),
        name=f"hng-v2-backup-{cycle}",
    )
    backup_started = time.perf_counter()
    backup_process.start()
    successful_report = False
    result: dict[str, object] | None = None
    try:
        while backup_process.is_alive():
            failures = worker_failures(active)
            if failures:
                raise RuntimeError(
                    f"worker exited during backup: {failures}"
                )
            if (
                time.perf_counter() - backup_started
                > args.backup_timeout_seconds
            ):
                backup_process.terminate()
                backup_process.join(timeout=30.0)
                raise TimeoutError("backup child timed out")
            next_sample = maybe_sample(
                processes=[*active, backup_process],
                started=started,
                next_sample=next_sample,
                resource_samples=resource_samples,
                events=events,
                args=args,
            )
            time.sleep(0.05)
        backup_process.join(timeout=5.0)
        try:
            report = output.get(timeout=5.0)
        except queue.Empty as exc:
            raise RuntimeError("backup child emitted no report") from exc
        if backup_process.exitcode != 0 or report.get("error"):
            raise RuntimeError(
                f"backup child failed: exit={backup_process.exitcode} "
                f"error={report.get('error')}"
            )
        result = report["result"]
        if expected_live is not None:
            result["expected_live_identity"] = (
                result["backup_logical"] == expected_live
            )
            result["passed"] = bool(
                result["passed"] and result["expected_live_identity"]
            )
        else:
            result["expected_live_identity"] = None
        result["writer_pause_acknowledgement_seconds"] = (
            acknowledgement_seconds
        )
        result["writer_pause_total_seconds"] = (
            time.perf_counter() - pause_started
        )
        v1.append_event(
            events, {"event": "backup_restore", **result}
        )
        successful_report = True
        return result, next_sample
    finally:
        if backup_process.is_alive():
            backup_process.terminate()
            backup_process.join(timeout=30.0)
        pause_event.clear()
        for acknowledgement in paused_acks:
            deadline = time.perf_counter() + 5.0
            while acknowledgement.is_set() and time.perf_counter() < deadline:
                time.sleep(0.01)
        resume_acknowledged = all(
            not acknowledgement.is_set()
            for acknowledgement in paused_acks
        )
        if result is not None:
            result["writer_resume_acknowledged"] = resume_acknowledged
        if restored_path.exists():
            remove_sqlite_temporary(restored_path)
        v1.append_event(events, {
            "event": "writers_resumed",
            "cycle": cycle,
            "acknowledged": resume_acknowledged,
        })
        if successful_report and not resume_acknowledged:
            raise RuntimeError(
                "writers did not acknowledge resume after backup"
            )


def run_soak(args: argparse.Namespace) -> dict[str, object]:
    if DATABASE.exists() or EVENTS.exists() or RESULT.exists() or RUN_DATA.exists():
        raise FileExistsError(
            "v2 sustained targets already exist; refusing overwrite or retry"
        )
    RUN_DATA.mkdir(parents=True, exist_ok=False)
    seed_store = SQLiteEvidenceStore(DATABASE)
    for index in range(args.seed_records):
        seed_store.append(v1.base_record(index, args.tenants))
    seed_store.close()

    context = mp.get_context("spawn")
    all_reports: list[dict[str, object]] = []
    backup_cycles: list[dict[str, object]] = []
    resource_samples: list[dict[str, object]] = []
    worker_epochs: list[dict[str, object]] = []
    active: list[Any] = []
    stop_event: Any = None
    pause_event: Any = None
    paused_acks: list[Any] = []
    started = time.perf_counter()
    deadline = started + args.duration_seconds
    next_backup = started + args.backup_interval_seconds
    next_sample = started
    epoch = 0
    try:
        with EVENTS.open("x", encoding="utf-8", newline="\n") as events:
            v1.append_event(events, {
                "event": "run_started",
                "config": frozen_config(args),
            })
            while time.perf_counter() < deadline:
                (
                    active,
                    stop_event,
                    pause_event,
                    paused_acks,
                    output,
                ) = start_workers(context, epoch, args)
                epoch_started = time.perf_counter()
                epoch_deadline = min(
                    deadline, epoch_started + args.rotation_seconds
                )
                v1.append_event(events, {
                    "event": "workers_started",
                    "epoch": epoch,
                    "pids": [process.pid for process in active],
                })
                while time.perf_counter() < epoch_deadline:
                    failures = worker_failures(active)
                    if failures:
                        raise RuntimeError(
                            f"worker exited before rotation: {failures}"
                        )
                    next_sample = maybe_sample(
                        processes=active,
                        started=started,
                        next_sample=next_sample,
                        resource_samples=resource_samples,
                        events=events,
                        args=args,
                    )
                    now = time.perf_counter()
                    if now >= next_backup:
                        cycle, next_sample = monitored_backup_cycle(
                            context=context,
                            cycle=len(backup_cycles) + 1,
                            active=active,
                            pause_event=pause_event,
                            paused_acks=paused_acks,
                            started=started,
                            next_sample=next_sample,
                            resource_samples=resource_samples,
                            events=events,
                            args=args,
                        )
                        backup_cycles.append(cycle)
                        next_backup += args.backup_interval_seconds
                    time.sleep(0.05)

                stop_workers(active, stop_event, pause_event)
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
                        and all(
                            process.exitcode == 0 for process in active
                        )
                        and all(
                            report.get("error") is None
                            for report in reports
                        )
                    ),
                }
                worker_epochs.append(epoch_result)
                all_reports.extend(reports)
                v1.append_event(events, {
                    "event": "workers_stopped",
                    **epoch_result,
                    "reports": reports,
                })
                active = []
                stop_event = pause_event = None
                paused_acks = []
                epoch += 1

            concurrent_duration = time.perf_counter() - started
            final_live = v1.logical_digest(DATABASE)
            final_pause = context.Event()
            final_cycle, next_sample = monitored_backup_cycle(
                context=context,
                cycle=len(backup_cycles) + 1,
                active=[],
                pause_event=final_pause,
                paused_acks=[],
                started=started,
                next_sample=next_sample,
                resource_samples=resource_samples,
                events=events,
                args=args,
                expected_live=final_live,
            )
            final_cycle["final_cycle"] = True
            backup_cycles.append(final_cycle)
            v1.append_event(events, {
                "event": "run_workload_complete",
                "concurrent_duration_seconds": concurrent_duration,
                "worker_epochs": len(worker_epochs),
                "backup_cycles": len(backup_cycles),
            })
    except BaseException:
        if active and stop_event is not None and pause_event is not None:
            try:
                stop_workers(active, stop_event, pause_event)
            except Exception:
                pass
        raise

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
    expected_count = args.seed_records + writes
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
    minimum_free = min(
        (int(sample["free_bytes"]) for sample in resource_samples),
        default=shutil.disk_usage(OUTPUT_DIR).free,
    )
    criteria = {
        "duration_reached": concurrent_duration >= args.duration_seconds,
        "minimum_writes_reached": writes >= args.minimum_writes,
        "minimum_reads_reached": reads >= args.minimum_reads,
        "minimum_worker_epochs_reached": (
            len(worker_epochs) >= args.minimum_worker_epochs
        ),
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
        "all_backup_restore_cycles_passed": (
            bool(backup_cycles)
            and all(item["passed"] for item in backup_cycles)
        ),
        "all_pause_acknowledgements_in_time": all(
            float(item["writer_pause_acknowledgement_seconds"])
            <= args.writer_pause_timeout_seconds
            for item in backup_cycles
        ),
        "all_writer_resumes_acknowledged": all(
            bool(item["writer_resume_acknowledged"])
            for item in backup_cycles
        ),
        "all_backup_children_in_time": all(
            float(item["duration_seconds"])
            <= args.backup_timeout_seconds
            for item in backup_cycles
        ),
        "final_record_count_exact": (
            final_live["evidence_count"] == expected_count
        ),
        "final_generation_exact": (
            final_live["generation"] == expected_count
        ),
        "final_backup_matches_live": bool(
            backup_cycles[-1].get("expected_live_identity")
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
        "runtime_disk_floor_respected": (
            minimum_free >= args.runtime_free_floor_bytes
        ),
    }
    passed = all(criteria.values())
    writer_latency = v1.histogram_summary(v1.merge_histograms(
        report["latency"] for report in writers
    ))
    reader_latency = v1.histogram_summary(v1.merge_histograms(
        report["latency"] for report in readers
    ))
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
            "sustained_2h_v2_write_quiesced_read_live_recovery"
        ),
        "status": "PASS" if passed else "FAIL",
        "predecessor_failure": (
            "breakthrough_eval/reliability/sustained_2h/INTERRUPTED.json"
        ),
        "claim_boundary": (
            "Two-hour local write-quiesced/read-live recovery protocol. "
            "Not uninterrupted-write backup, crash, power-loss, actual "
            "disk-full, distributed, leak-absence, or production evidence."
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
        "backup_pause": {
            "total_seconds": sum(
                float(item["writer_pause_total_seconds"])
                for item in backup_cycles
            ),
            "maximum_seconds": max(
                (
                    float(item["writer_pause_total_seconds"])
                    for item in backup_cycles
                ),
                default=0.0,
            ),
        },
        "final_live_logical": final_live,
        "expected_final_evidence_count": expected_count,
        "resource_observations": {
            "samples": len(resource_samples),
            "maximum_process_rss_bytes": max_rss,
            "maximum_process_handles": max_handles,
            "minimum_free_bytes": minimum_free,
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
    if v1.psutil is None:
        raise RuntimeError("psutil is required for v2 execution")
    if not PREPARED.is_file():
        raise FileNotFoundError(PREPARED)
    if RESULT.exists() or EVENTS.exists() or RUN_DATA.exists():
        raise FileExistsError(
            "refusing overwrite/retry of v2 sustained artifacts"
        )
    head = v1.git("rev-parse", "HEAD")
    if head != args.preregistered_commit:
        raise RuntimeError(
            f"HEAD {head} != preregistered commit "
            f"{args.preregistered_commit}"
        )
    origin = v1.git("rev-parse", "origin/main")
    if origin != head:
        raise RuntimeError(
            f"origin/main {origin} != preregistered HEAD {head}"
        )
    status = v1.git("status", "--porcelain", "--untracked-files=all")
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
    parser.add_argument("--rotation-seconds", type=float, default=900.0)
    parser.add_argument("--minimum-worker-epochs", type=int, default=8)
    parser.add_argument(
        "--backup-interval-seconds", type=float, default=600.0
    )
    parser.add_argument(
        "--writer-pause-timeout-seconds", type=float, default=30.0
    )
    parser.add_argument(
        "--backup-timeout-seconds", type=float, default=180.0
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
    parser.add_argument(
        "--runtime-free-floor-bytes", type=int, default=30_000_000_000
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
        args.minimum_worker_epochs,
        args.backup_interval_seconds,
        args.writer_pause_timeout_seconds,
        args.backup_timeout_seconds,
        args.sample_interval_seconds,
        args.minimum_backup_cycles,
        args.minimum_resource_samples,
    )
    if any(value <= 0 for value in positive):
        parser.error("all duration, count, worker, and interval values must be positive")
    if args.seed_records < args.tenants:
        parser.error(
            "seed-records must be at least as large as tenants"
        )
    if args.seed_records % args.tenants:
        parser.error("seed-records must be divisible by tenants")
    if args.runtime_free_floor_bytes >= args.minimum_free_bytes:
        parser.error(
            "runtime free floor must be below preflight free minimum"
        )
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
            "benchmark": (
                "sustained_2h_v2_write_quiesced_read_live_recovery"
            ),
            "status": "ERROR",
            "created_at": v1.utc_now(),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "preregistered_commit": args.preregistered_commit,
            "command": [sys.executable, *sys.argv],
            "partial_events": (
                display_path(EVENTS) if EVENTS.exists() else None
            ),
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
