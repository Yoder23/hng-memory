#!/usr/bin/env python3
"""Independent-sampler wrapper for the shared-SQLite handle matrix."""

from __future__ import annotations

import multiprocessing as mp
import os
from pathlib import Path
import signal
import sys
import threading
import time
import traceback
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts import shared_sqlite_handle_diagnostic as base  # noqa: E402


OUTPUT_DIR = (
    ROOT / "breakthrough_eval" / "reliability" /
    "shared_sqlite_handle_diagnostic_v2"
)
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
RUN_DATA = OUTPUT_DIR / "run_data"
WRAPPER = Path(__file__).resolve()
BASE_WRAPPER = base.WRAPPER
PREDECESSOR_RESULT = (
    ROOT / "breakthrough_eval" / "reliability" /
    "shared_sqlite_handle_diagnostic" / "RESULTS.json"
)


def threaded_matrix_worker(
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
    sampler_error: list[str] = []
    sampler_stop = threading.Event()
    sampler: threading.Thread | None = None
    try:
        if base.sustained.psutil is None or not hasattr(
            base.sustained.psutil.Process(), "num_handles"
        ):
            raise RuntimeError("Windows psutil num_handles is required")
        if database is not None:
            store = base.SQLiteEvidenceStore(database)
        process = base.sustained.psutil.Process(os.getpid())
        ready_event.set()
        if not start_event.wait(timeout=60.0):
            raise TimeoutError("condition start timed out")
        interval = float(args_payload["sample_interval_seconds"])
        tenants = int(args_payload["tenants"])
        seed_records = int(args_payload["seed_records"])

        def sample_loop() -> None:
            nonlocal samples
            try:
                with Path(log_path).open(
                    "x", encoding="utf-8", newline="\n"
                ) as log:
                    next_sample = time.monotonic()
                    while not sampler_stop.is_set():
                        wall_ns = time.time_ns()
                        base.observer.append_fsynced(log, {
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
                        next_sample += interval
                        sampler_stop.wait(max(0.0, next_sample - time.monotonic()))
            except BaseException as exc:
                sampler_error.append(
                    f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
                )

        sampler = threading.Thread(
            target=sample_loop,
            name=f"handle-sampler-{worker_index:02d}",
            daemon=True,
        )
        sampler.start()
        while not stop_event.is_set():
            if sampler_error:
                raise RuntimeError(sampler_error[0])
            if condition == "idle_12":
                stop_event.wait(0.01)
                continue
            if role == "writer":
                store.append(base.sustained.worker_record(
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
        sampler_stop.set()
        sampler.join(timeout=10.0)
        if sampler.is_alive():
            raise RuntimeError("sampler thread failed to stop")
        if sampler_error:
            raise RuntimeError(sampler_error[0])
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
        sampler_stop.set()
        if sampler is not None and sampler.is_alive():
            sampler.join(timeout=10.0)
        if store is not None:
            store.close()


def classify_v2(
    results: Mapping[str, Mapping[str, Any]], args: Any,
) -> str:
    if not all(bool(item["valid"]) for item in results.values()):
        return "INVALID"
    idle = results["idle_12"]
    isolated = results["isolated_sqlite_12"]
    shared = (
        results["shared_sqlite_12_a"],
        results["shared_sqlite_12_b"],
    )
    if (
        float(idle["median_slope_handles_per_minute"])
        >= args.process_count_support_slope_handles_per_minute
    ):
        return "SUPPORTS_PROCESS_COUNT_CAUSE"
    controls_bounded = (
        float(idle["maximum_slope_handles_per_minute"])
        < args.control_maximum_slope_handles_per_minute
        and float(isolated["maximum_slope_handles_per_minute"])
        < args.control_maximum_slope_handles_per_minute
    )
    shared_supported = all(
        float(item["median_slope_handles_per_minute"])
        >= args.shared_support_slope_handles_per_minute
        and sum(
            float(child["slope_handles_per_minute"])
            >= args.shared_support_slope_handles_per_minute
            for child in item["per_child"]
        ) >= 10
        for item in shared
    )
    if controls_bounded and shared_supported:
        return "SUPPORTS_SHARED_SQLITE_CAUSE"
    if all(
        float(item["median_slope_handles_per_minute"])
        < args.control_maximum_slope_handles_per_minute
        for item in results.values()
    ):
        return "DOES_NOT_REPRODUCE"
    return "INCONCLUSIVE"


def configure() -> None:
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
        PROTOCOL, WRAPPER, BASE_WRAPPER, PREDECESSOR_RESULT,
    )
    base.matrix_worker = threaded_matrix_worker
    base.classify = classify_v2


def freeze_shared_lower_bound() -> None:
    if not any(
        value == "--shared-support-slope-handles-per-minute"
        or value.startswith("--shared-support-slope-handles-per-minute=")
        for value in sys.argv
    ):
        sys.argv.extend([
            "--shared-support-slope-handles-per-minute", "10",
        ])


def main() -> int:
    configure()
    freeze_shared_lower_bound()
    return base.main()


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
