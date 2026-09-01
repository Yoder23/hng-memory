#!/usr/bin/env python3
"""Preregistered test linking Section growth to SQLite WAL-index units."""

from __future__ import annotations

from collections import Counter
import multiprocessing as mp
import os
from pathlib import Path
import signal
import statistics
import sys
import threading
import time
import traceback
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts import shared_sqlite_handle_diagnostic as base  # noqa: E402
from breakthrough_eval.scripts import shared_sqlite_handle_type_diagnostic as typed  # noqa: E402
from breakthrough_eval.scripts import shared_sqlite_handle_type_diagnostic_v3 as typed_v3  # noqa: E402
from breakthrough_eval.scripts import windows_handle_snapshot  # noqa: E402


OUTPUT_DIR = (
    ROOT / "breakthrough_eval" / "reliability" /
    "shared_sqlite_wal_index_diagnostic"
)
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
MECHANISM_BASIS = OUTPUT_DIR / "MECHANISM_BASIS.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
RUN_DATA = OUTPUT_DIR / "run_data"
WRAPPER = Path(__file__).resolve()
PREDECESSOR_RESULT = typed_v3.RESULT
WAL_INDEX_UNIT_BYTES = 32768
MAXIMUM_UNIT_DELTA_ERROR = 1


def frozen_config(args: Any) -> dict[str, object]:
    return {
        **typed.frozen_config(args),
        "wal_index_unit_bytes": WAL_INDEX_UNIT_BYTES,
        "maximum_section_to_shm_unit_delta_error": MAXIMUM_UNIT_DELTA_ERROR,
    }


def file_state(database: str | None) -> dict[str, int | None]:
    if database is None:
        return {
            "database_bytes": None,
            "shm_bytes": None,
            "shm_units": None,
            "wal_bytes": None,
        }
    path = Path(database)
    shm = Path(f"{database}-shm")
    wal = Path(f"{database}-wal")
    shm_bytes = shm.stat().st_size if shm.exists() else 0
    return {
        "database_bytes": path.stat().st_size,
        "shm_bytes": shm_bytes,
        "shm_units": shm_bytes // WAL_INDEX_UNIT_BYTES,
        "wal_bytes": wal.stat().st_size if wal.exists() else 0,
    }


def mapping_worker(
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
    types_start: Counter[str] | None = None
    types_end: Counter[str] | None = None
    files_start: dict[str, int | None] | None = None
    files_end: dict[str, int | None] | None = None
    try:
        if base.sustained.psutil is None or not hasattr(
            base.sustained.psutil.Process(), "num_handles"
        ):
            raise RuntimeError("Windows psutil num_handles is required")
        if database is not None:
            store = base.SQLiteEvidenceStore(database)
        files_start = file_state(database)
        process = base.sustained.psutil.Process(os.getpid())
        ready_event.set()
        if not start_event.wait(timeout=60.0):
            raise TimeoutError("condition start timed out")
        types_start = windows_handle_snapshot.current_process_handle_types()
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
                            "file_state": file_state(database),
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
            name=f"wal-index-sampler-{worker_index:02d}",
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
        files_end = file_state(database)
        types_end = windows_handle_snapshot.current_process_handle_types()
        all_types = set(types_start) | set(types_end)
        type_delta = {
            name: int(types_end.get(name, 0) - types_start.get(name, 0))
            for name in sorted(all_types)
        }
        output.put({
            "condition": condition,
            "role": role,
            "worker_index": worker_index,
            "pid": os.getpid(),
            "samples": samples,
            "operations": operations,
            "missing": missing,
            "malformed": malformed,
            "file_state_start": files_start,
            "file_state_end": files_end,
            "handle_types_start": dict(sorted(types_start.items())),
            "handle_types_end": dict(sorted(types_end.items())),
            "handle_type_delta": type_delta,
            "handle_type_total_start": sum(types_start.values()),
            "handle_type_total_end": sum(types_end.values()),
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
            "file_state_start": files_start,
            "file_state_end": files_end,
            "handle_types_start": dict(types_start or {}),
            "handle_types_end": dict(types_end or {}),
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


def mapping_analysis(
    results: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    analysis = {}
    for condition, result in results.items():
        rows = []
        for report in result["reports"]:
            start = report["file_state_start"]
            end = report["file_state_end"]
            shm_start = start["shm_units"]
            shm_end = end["shm_units"]
            shm_delta = (
                None if shm_start is None or shm_end is None
                else int(shm_end) - int(shm_start)
            )
            section_delta = int(report["handle_type_delta"].get("Section", 0))
            rows.append({
                "worker_index": report["worker_index"],
                "role": report["role"],
                "section_delta": section_delta,
                "shm_unit_delta": shm_delta,
                "absolute_delta_error": (
                    None if shm_delta is None
                    else abs(section_delta - shm_delta)
                ),
                "file_state_start": start,
                "file_state_end": end,
            })
        measurable = [row for row in rows if row["shm_unit_delta"] is not None]
        analysis[condition] = {
            "per_child": rows,
            "median_section_delta": statistics.median(
                row["section_delta"] for row in rows
            ) if rows else None,
            "median_shm_unit_delta": statistics.median(
                row["shm_unit_delta"] for row in measurable
            ) if measurable else None,
            "maximum_absolute_delta_error": max(
                row["absolute_delta_error"] for row in measurable
            ) if measurable else None,
        }
    return analysis


def classify_mapping(
    results: Mapping[str, Mapping[str, Any]], args: Any,
) -> str:
    if not all(bool(item["valid"]) for item in results.values()):
        return "INVALID"
    if typed.classify_typed(results, args) != "IDENTIFIES_DOMINANT_HANDLE_TYPE":
        return "INCONCLUSIVE"
    analysis = mapping_analysis(results)
    shared_names = ("shared_sqlite_12_a", "shared_sqlite_12_b")
    shared_matches = all(
        item["median_shm_unit_delta"] is not None
        and float(item["median_shm_unit_delta"])
        >= typed.MINIMUM_DOMINANT_TYPE_DELTA
        and item["median_section_delta"] == item["median_shm_unit_delta"]
        and int(item["maximum_absolute_delta_error"])
        <= MAXIMUM_UNIT_DELTA_ERROR
        for name in shared_names
        for item in [analysis[name]]
    )
    controls_match = all(
        analysis[name]["median_section_delta"] == 0
        and analysis[name]["median_shm_unit_delta"] in (None, 0)
        for name in ("idle_12", "isolated_sqlite_12")
    )
    sizes_aligned = all(
        state[key] is None
        or int(state[key]) % WAL_INDEX_UNIT_BYTES == 0
        for result in results.values()
        for report in result["reports"]
        for state in (
            report["file_state_start"], report["file_state_end"]
        )
        for key in ("shm_bytes",)
    )
    if shared_matches and controls_match and sizes_aligned:
        return "IDENTIFIES_WAL_INDEX_SECTION_MAPPING"
    return "INCONCLUSIVE"


def run_mapping_matrix(args: Any) -> dict[str, Any]:
    result = typed.run_typed_matrix(args)
    result["benchmark"] = "shared_sqlite_wal_index_section_mapping_diagnostic"
    result["mapping_analysis"] = mapping_analysis(result["conditions"])
    result["claim_boundary"] = (
        "SQLite WAL-index mechanism diagnostic only; never HNG, storage, "
        "recovery, production, or sustained-run qualification evidence."
    )
    return result


def configure() -> None:
    typed_v3.configure()
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
        MECHANISM_BASIS,
        WRAPPER,
        typed_v3.WRAPPER,
        typed.WRAPPER,
        typed.BASE_WRAPPER,
        typed.HANDLE_SNAPSHOT,
        typed.PREDECESSOR_RESULT,
        PREDECESSOR_RESULT,
    )
    base.frozen_config = frozen_config
    base.matrix_worker = mapping_worker
    base.run_condition = typed_v3.queue_safe_run_condition
    base.classify = classify_mapping
    base.run_matrix = run_mapping_matrix


def main() -> int:
    configure()
    typed.freeze_defaults()
    return base.main()


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
