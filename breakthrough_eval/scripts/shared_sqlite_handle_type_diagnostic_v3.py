#!/usr/bin/env python3
"""Queue-safe replication of the shared-SQLite handle-type diagnostic."""

from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path
import queue
import statistics
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts import shared_sqlite_handle_diagnostic as base  # noqa: E402
from breakthrough_eval.scripts import shared_sqlite_handle_type_diagnostic as typed  # noqa: E402
from breakthrough_eval.scripts import shared_sqlite_handle_type_diagnostic_v2 as typed_v2  # noqa: E402


OUTPUT_DIR = (
    ROOT / "breakthrough_eval" / "reliability" /
    "shared_sqlite_handle_type_diagnostic_v3"
)
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
RUN_DATA = OUTPUT_DIR / "run_data"
WRAPPER = Path(__file__).resolve()
PREDECESSOR_RESULT = typed_v2.RESULT


def queue_safe_run_condition(
    context: Any,
    condition: str,
    condition_epoch: int,
    args: Any,
    events: Any,
) -> dict[str, Any]:
    condition_dir = base.RUN_DATA / condition
    condition_dir.mkdir(parents=True, exist_ok=False)
    workers = args.writer_workers + args.reader_workers
    databases = base.prepare_condition_databases(
        condition_dir, condition, workers, args.seed_records, args.tenants
    )
    start_ns = context.Value("q", 0)
    start_event = context.Event()
    stop_event = context.Event()
    ready = [context.Event() for _ in range(workers)]
    output = context.Queue()
    payload = base.frozen_config(args)
    roles = ["writer"] * args.writer_workers + [
        "reader"
    ] * args.reader_workers
    processes = [
        context.Process(
            target=base.matrix_worker,
            args=(
                condition, roles[index], index, databases[index],
                condition_epoch, payload, start_ns, start_event, stop_event,
                ready[index], output,
                str(condition_dir / f"worker-{index:02d}.jsonl"),
            ),
            name=f"typed-handle-v3-{condition}-{index:02d}",
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
    base.observer.append_fsynced(events, {
        "condition": condition,
        "created_at": base.sustained.utc_now(),
        "event": "condition_started",
        "pids": [process.pid for process in processes],
    })
    start_event.set()
    deadline = time.monotonic() + args.condition_seconds
    reports: list[dict[str, Any]] = []
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
        report_deadline = time.monotonic() + 60.0
        while len(reports) < workers and time.monotonic() < report_deadline:
            try:
                reports.append(output.get(timeout=0.2))
            except queue.Empty:
                continue
        join_deadline = time.monotonic() + 60.0
        for process in processes:
            process.join(timeout=max(0.0, join_deadline - time.monotonic()))
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10.0)
        while len(reports) < workers:
            try:
                reports.append(output.get_nowait())
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
        stats = base.handle_stats(samples)
        per_child.append({
            "worker_index": index, "role": role, **stats,
        })
        artifacts[base.display_path(path)] = {
            "bytes": path.stat().st_size,
            "sha256": base.observer.sha256_file(path),
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
        "handle_type_snapshots_complete": (
            len(reports) == workers
            and all(
                report.get("handle_types_start")
                and report.get("handle_types_end")
                and "handle_type_delta" in report
                and report.get("handle_types_start", {}).get(
                    "<query-error>", 0
                ) == 0
                and report.get("handle_types_end", {}).get(
                    "<query-error>", 0
                ) == 0
                for report in reports
            )
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
        "report_drain_order": "concurrent_before_join",
    }
    base.observer.append_fsynced(events, {
        "condition": condition,
        "created_at": base.sustained.utc_now(),
        "event": "condition_completed",
        "median_slope_handles_per_minute": result[
            "median_slope_handles_per_minute"
        ],
        "reports": len(reports),
        "valid": result["valid"],
    })
    for process in processes:
        process.close()
    output.close()
    output.join_thread()
    return result


def configure() -> None:
    typed_v2.configure()
    base.OUTPUT_DIR = OUTPUT_DIR
    base.PROTOCOL = PROTOCOL
    base.PREPARED = PREPARED
    base.RESULT = RESULT
    base.EVENTS = EVENTS
    base.RUN_DATA = RUN_DATA
    base.WRAPPER = WRAPPER
    base.V2_FAILURE = PREDECESSOR_RESULT
    base.OBSERVER_RESULT = PREDECESSOR_RESULT
    base.SOURCE_FILES = (
        PROTOCOL,
        WRAPPER,
        typed_v2.WRAPPER,
        typed.WRAPPER,
        typed.BASE_WRAPPER,
        typed.HANDLE_SNAPSHOT,
        typed.PREDECESSOR_RESULT,
        PREDECESSOR_RESULT,
    )
    base.run_condition = queue_safe_run_condition


def main() -> int:
    configure()
    typed.freeze_defaults()
    return base.main()


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
