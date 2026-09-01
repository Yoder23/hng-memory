#!/usr/bin/env python3
"""Preregistered handle-type follow-up for the shared-SQLite matrix."""

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
from breakthrough_eval.scripts import windows_handle_snapshot  # noqa: E402


OUTPUT_DIR = (
    ROOT / "breakthrough_eval" / "reliability" /
    "shared_sqlite_handle_type_diagnostic"
)
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
RUN_DATA = OUTPUT_DIR / "run_data"
WRAPPER = Path(__file__).resolve()
BASE_WRAPPER = base.WRAPPER
HANDLE_SNAPSHOT = Path(windows_handle_snapshot.__file__).resolve()
PREDECESSOR_RESULT = (
    ROOT / "breakthrough_eval" / "reliability" /
    "shared_sqlite_handle_diagnostic_v2" / "RESULTS.json"
)

MINIMUM_DOMINANT_TYPE_DELTA = 10.0
MINIMUM_DOMINANCE_FRACTION = 0.80
CONTROL_MAXIMUM_TYPE_DELTA = 2

BASE_FROZEN_CONFIG = base.frozen_config
BASE_RUN_CONDITION = base.run_condition
BASE_RUN_MATRIX = base.run_matrix


def frozen_config(args: Any) -> dict[str, object]:
    return {
        **BASE_FROZEN_CONFIG(args),
        "minimum_dominant_type_delta": MINIMUM_DOMINANT_TYPE_DELTA,
        "minimum_dominance_fraction": MINIMUM_DOMINANCE_FRACTION,
        "control_maximum_type_delta": CONTROL_MAXIMUM_TYPE_DELTA,
        "handle_type_snapshot_method": (
            "NtQuerySystemInformation(SystemExtendedHandleInformation) plus "
            "NtQueryObject(ObjectTypeInformation)"
        ),
    }


def typed_matrix_worker(
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
            name=f"typed-handle-sampler-{worker_index:02d}",
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


def run_typed_condition(*args: Any, **kwargs: Any) -> dict[str, Any]:
    result = BASE_RUN_CONDITION(*args, **kwargs)
    complete = all(
        report.get("handle_types_start")
        and report.get("handle_types_end")
        and "handle_type_delta" in report
        and report.get("handle_types_start", {}).get("<query-error>", 0) == 0
        and report.get("handle_types_end", {}).get("<query-error>", 0) == 0
        for report in result["reports"]
    )
    result["validity"]["handle_type_snapshots_complete"] = complete
    result["valid"] = all(result["validity"].values())
    return result


def summarize_types(
    results: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    summaries = {}
    for condition, result in results.items():
        reports = result["reports"]
        type_names = sorted({
            name
            for report in reports
            for name in report.get("handle_type_delta", {})
        })
        medians = {
            name: statistics.median(
                int(report["handle_type_delta"].get(name, 0))
                for report in reports
            )
            for name in type_names
        }
        positive_total = sum(max(0.0, float(value)) for value in medians.values())
        dominant = max(
            medians,
            key=lambda name: (medians[name], name),
            default=None,
        )
        dominant_delta = float(medians.get(dominant, 0.0)) if dominant else 0.0
        summaries[condition] = {
            "median_delta_by_type": medians,
            "dominant_type": dominant,
            "dominant_type_median_delta": dominant_delta,
            "dominance_fraction_of_positive_median_delta": (
                dominant_delta / positive_total if positive_total else 0.0
            ),
        }
    return summaries


def classify_typed(
    results: Mapping[str, Mapping[str, Any]], args: Any,
) -> str:
    if not all(bool(item["valid"]) for item in results.values()):
        return "INVALID"
    summaries = summarize_types(results)
    shared_names = ("shared_sqlite_12_a", "shared_sqlite_12_b")
    shared = [summaries[name] for name in shared_names]
    candidates = {item["dominant_type"] for item in shared}
    reproduced = all(
        float(results[name]["median_slope_handles_per_minute"])
        >= args.shared_support_slope_handles_per_minute
        and sum(
            float(child["slope_handles_per_minute"])
            >= args.shared_support_slope_handles_per_minute
            for child in results[name]["per_child"]
        ) >= 10
        for name in shared_names
    )
    controls_bounded = all(
        float(results[name]["maximum_slope_handles_per_minute"])
        < args.control_maximum_slope_handles_per_minute
        for name in ("idle_12", "isolated_sqlite_12")
    )
    if len(candidates) == 1:
        candidate = next(iter(candidates))
        control_type_bounded = all(
            max(
                int(report["handle_type_delta"].get(candidate, 0))
                for report in results[name]["reports"]
            ) <= CONTROL_MAXIMUM_TYPE_DELTA
            for name in ("idle_12", "isolated_sqlite_12")
        )
        type_dominant = all(
            float(item["dominant_type_median_delta"])
            >= MINIMUM_DOMINANT_TYPE_DELTA
            and float(item["dominance_fraction_of_positive_median_delta"])
            >= MINIMUM_DOMINANCE_FRACTION
            for item in shared
        )
        if reproduced and controls_bounded and control_type_bounded and type_dominant:
            return "IDENTIFIES_DOMINANT_HANDLE_TYPE"
    if all(
        float(item["median_slope_handles_per_minute"])
        < args.control_maximum_slope_handles_per_minute
        for item in results.values()
    ):
        return "DOES_NOT_REPRODUCE"
    return "INCONCLUSIVE"


def run_typed_matrix(args: Any) -> dict[str, Any]:
    result = BASE_RUN_MATRIX(args)
    result["benchmark"] = "shared_sqlite_child_handle_type_diagnostic"
    analysis = summarize_types(result["conditions"])
    result["handle_type_analysis"] = analysis
    shared_types = {
        analysis[name]["dominant_type"]
        for name in ("shared_sqlite_12_a", "shared_sqlite_12_b")
    }
    result["dominant_handle_type"] = (
        next(iter(shared_types)) if len(shared_types) == 1 else None
    )
    result["claim_boundary"] = (
        "Windows handle-type mechanism diagnostic only; never HNG, storage, "
        "recovery, production, or sustained-run qualification evidence."
    )
    return result


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
        PROTOCOL, WRAPPER, BASE_WRAPPER, HANDLE_SNAPSHOT, PREDECESSOR_RESULT,
    )
    base.frozen_config = frozen_config
    base.matrix_worker = typed_matrix_worker
    base.run_condition = run_typed_condition
    base.classify = classify_typed
    base.run_matrix = run_typed_matrix


def freeze_defaults() -> None:
    options = {
        "--condition-seconds": "60",
        "--minimum-samples-per-child": "50",
        "--shared-support-slope-handles-per-minute": "10",
    }
    for option, value in options.items():
        if not any(
            item == option or item.startswith(f"{option}=") for item in sys.argv
        ):
            sys.argv.extend([option, value])


def main() -> int:
    configure()
    freeze_defaults()
    return base.main()


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
