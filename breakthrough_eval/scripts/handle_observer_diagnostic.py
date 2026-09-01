#!/usr/bin/env python3
"""Preregistered child self-sampling diagnostic for external observer effects."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import signal
import sqlite3
import statistics
import sys
import time
import traceback
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts import sustained_reliability as shared  # noqa: E402


OUTPUT_DIR = (
    ROOT / "breakthrough_eval" / "reliability" /
    "handle_observer_diagnostic"
)
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
PULSES = OUTPUT_DIR / "pulses.jsonl"
STATE = OUTPUT_DIR / "main_state.json"
RUN_DATA = OUTPUT_DIR / "run_data"
WRAPPER = Path(__file__).resolve()
V2_FAILURE = (
    ROOT / "breakthrough_eval" / "reliability" / "sustained_2h_v2" /
    "FAILURE_ANALYSIS.json"
)
SOURCE_FILES = (PROTOCOL, WRAPPER, V2_FAILURE)
VARIANTS = ("idle", "event_poll", "sqlite_read", "sqlite_write")


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_hashes() -> dict[str, str]:
    return {display_path(path): sha256_file(path) for path in SOURCE_FILES}


def frozen_config(args: argparse.Namespace) -> dict[str, object]:
    return {
        "warmup_seconds": args.warmup_seconds,
        "baseline_seconds": args.baseline_seconds,
        "external_seconds": args.external_seconds,
        "recovery_seconds": args.recovery_seconds,
        "sample_interval_seconds": args.sample_interval_seconds,
        "expected_pulses": args.expected_pulses,
        "minimum_samples_per_phase": args.minimum_samples_per_phase,
        "support_slope_margin_handles_per_minute": (
            args.support_slope_margin_handles_per_minute
        ),
        "support_minimum_external_net_handles": (
            args.support_minimum_external_net_handles
        ),
        "refute_slope_tolerance_handles_per_minute": (
            args.refute_slope_tolerance_handles_per_minute
        ),
        "refute_maximum_external_net_handles": (
            args.refute_maximum_external_net_handles
        ),
        "variants": list(VARIANTS),
        "multiprocessing_start_method": "spawn",
    }


def prepared_payload(args: argparse.Namespace) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "PREPARED_NOT_EXECUTED",
        "created_at": shared.utc_now(),
        "motivation": display_path(V2_FAILURE),
        "hypothesis_status_before_execution": "UNPROVEN",
        "config": frozen_config(args),
        "source_sha256": source_hashes(),
        "commands": {
            "main": [
                sys.executable, display_path(WRAPPER),
                "--preregistered-commit", "COMMIT",
            ],
            "pulse": [
                sys.executable, display_path(WRAPPER),
                "--pulse-ordinal", "N",
                "--preregistered-commit", "COMMIT",
            ],
        },
        "claim_boundary": (
            "Environment attribution diagnostic only. It cannot qualify HNG, "
            "storage, recovery, production reliability, or the failed v2 run."
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


def phase_for_elapsed(elapsed: float, args: argparse.Namespace) -> str:
    baseline_start = args.warmup_seconds
    external_start = baseline_start + args.baseline_seconds
    recovery_start = external_start + args.external_seconds
    if elapsed < baseline_start:
        return "warmup"
    if elapsed < external_start:
        return "baseline"
    if elapsed < recovery_start:
        return "external"
    return "recovery"


def append_fsynced(handle: Any, payload: Mapping[str, Any]) -> None:
    handle.write(json.dumps(payload, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def worker(
    variant: str,
    database: str | None,
    start_ns: Any,
    start_event: Any,
    stop_event: Any,
    auxiliary_event: Any,
    ready_event: Any,
    output: Any,
    log_path: str,
    args_payload: Mapping[str, Any],
) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    connection: sqlite3.Connection | None = None
    samples = operations = 0
    try:
        if shared.psutil is None or not hasattr(
            shared.psutil.Process(), "num_handles"
        ):
            raise RuntimeError("Windows psutil num_handles is required")
        if variant in {"sqlite_read", "sqlite_write"}:
            if database is None:
                raise RuntimeError("database path missing")
            connection = sqlite3.connect(database, timeout=30.0)
        process = shared.psutil.Process(os.getpid())
        ready_event.set()
        if not start_event.wait(timeout=60.0):
            raise TimeoutError("worker start timed out")
        interval = float(args_payload["sample_interval_seconds"])
        next_sample = time.monotonic()
        with Path(log_path).open("x", encoding="utf-8", newline="\n") as log:
            while not stop_event.is_set():
                now = time.monotonic()
                if now >= next_sample:
                    wall_ns = time.time_ns()
                    elapsed = (wall_ns - int(start_ns.value)) / 1_000_000_000
                    append_fsynced(log, {
                        "created_at_ns": wall_ns,
                        "elapsed_seconds": elapsed,
                        "handles": process.num_handles(),
                        "operations": operations,
                        "phase": phase_for_elapsed(
                            elapsed, argparse.Namespace(**args_payload)
                        ),
                        "pid": os.getpid(),
                        "rss_bytes": process.memory_info().rss,
                        "threads": process.num_threads(),
                        "variant": variant,
                    })
                    samples += 1
                    while next_sample <= now:
                        next_sample += interval
                if variant == "idle":
                    time.sleep(0.02)
                elif variant == "event_poll":
                    auxiliary_event.is_set()
                    stop_event.wait(0.02)
                elif variant == "sqlite_read":
                    connection.execute(
                        "SELECT value FROM items WHERE id=?",
                        (operations % 100,),
                    ).fetchone()
                    operations += 1
                    time.sleep(0.01)
                elif variant == "sqlite_write":
                    connection.execute(
                        "INSERT INTO writes(value) VALUES(?)", (operations,)
                    )
                    connection.commit()
                    operations += 1
                    time.sleep(0.01)
                else:
                    raise RuntimeError(f"unknown variant: {variant}")
        output.put({
            "variant": variant, "pid": os.getpid(), "samples": samples,
            "operations": operations, "error": None,
        })
    except BaseException as exc:
        output.put({
            "variant": variant, "pid": os.getpid(), "samples": samples,
            "operations": operations,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        })
        raise
    finally:
        if connection is not None:
            connection.close()


def phase_stats(samples: Sequence[Mapping[str, Any]], phase: str) -> dict[str, Any]:
    selected = [item for item in samples if item["phase"] == phase]
    if len(selected) < 2:
        return {"samples": len(selected), "slope_handles_per_minute": None,
                "net_handles": None, "first_handles": None,
                "last_handles": None}
    elapsed = float(selected[-1]["elapsed_seconds"]) - float(
        selected[0]["elapsed_seconds"]
    )
    net = int(selected[-1]["handles"]) - int(selected[0]["handles"])
    return {
        "samples": len(selected),
        "elapsed_seconds": elapsed,
        "first_handles": int(selected[0]["handles"]),
        "last_handles": int(selected[-1]["handles"]),
        "net_handles": net,
        "slope_handles_per_minute": net / (elapsed / 60.0),
    }


def analyze(
    samples_by_variant: Mapping[str, Sequence[Mapping[str, Any]]],
    pulses: Sequence[Mapping[str, Any]],
    reports: Sequence[Mapping[str, Any]],
    exitcodes: Sequence[int | None],
    args: argparse.Namespace,
) -> dict[str, Any]:
    per_variant = {
        variant: {
            phase: phase_stats(samples_by_variant[variant], phase)
            for phase in ("baseline", "external", "recovery")
        }
        for variant in VARIANTS
    }
    slopes = {
        phase: [
            float(per_variant[variant][phase]["slope_handles_per_minute"])
            for variant in VARIANTS
            if per_variant[variant][phase]["slope_handles_per_minute"] is not None
        ]
        for phase in ("baseline", "external", "recovery")
    }
    nets = [
        int(per_variant[variant]["external"]["net_handles"])
        for variant in VARIANTS
        if per_variant[variant]["external"]["net_handles"] is not None
    ]
    median_slopes = {
        phase: statistics.median(values) if values else None
        for phase, values in slopes.items()
    }
    median_external_net = statistics.median(nets) if nets else None
    external_start = args.warmup_seconds + args.baseline_seconds
    external_end = external_start + args.external_seconds
    pulse_ordinals = [int(item["ordinal"]) for item in pulses]
    validity = {
        "all_children_reported": len(reports) == len(VARIANTS),
        "all_child_exitcodes_zero": all(code == 0 for code in exitcodes),
        "no_child_errors": all(item.get("error") is None for item in reports),
        "exact_pulse_ordinals": (
            sorted(pulse_ordinals) == list(range(1, args.expected_pulses + 1))
        ),
        "all_pulses_in_external_phase": all(
            external_start <= float(item["elapsed_seconds"]) < external_end
            for item in pulses
        ),
        "minimum_samples_each_phase": all(
            per_variant[variant][phase]["samples"]
            >= args.minimum_samples_per_phase
            for variant in VARIANTS
            for phase in ("baseline", "external", "recovery")
        ),
    }
    valid = all(validity.values())
    baseline = median_slopes["baseline"]
    external = median_slopes["external"]
    recovery = median_slopes["recovery"]
    if (
        valid and external is not None and baseline is not None
        and recovery is not None and median_external_net is not None
        and external >= max(baseline, recovery)
        + args.support_slope_margin_handles_per_minute
        and median_external_net >= args.support_minimum_external_net_handles
    ):
        outcome = "SUPPORTS_OBSERVER_EFFECT"
    elif (
        valid and external is not None and baseline is not None
        and median_external_net is not None
        and abs(external - baseline)
        <= args.refute_slope_tolerance_handles_per_minute
        and median_external_net < args.refute_maximum_external_net_handles
    ):
        outcome = "REFUTES_OBSERVER_EFFECT_AT_THRESHOLD"
    else:
        outcome = "INCONCLUSIVE" if valid else "INVALID"
    return {
        "validity": validity,
        "valid": valid,
        "outcome": outcome,
        "per_variant": per_variant,
        "median_slope_handles_per_minute": median_slopes,
        "median_external_net_handles": median_external_net,
        "pulse_count": len(pulses),
        "pulse_ordinals": pulse_ordinals,
    }


def setup_databases() -> dict[str, str | None]:
    paths: dict[str, str | None] = {"idle": None, "event_poll": None}
    read_path = RUN_DATA / "read.sqlite"
    connection = sqlite3.connect(read_path)
    connection.execute("CREATE TABLE items(id INTEGER PRIMARY KEY,value TEXT)")
    connection.executemany(
        "INSERT INTO items(id,value) VALUES(?,?)",
        [(index, f"value-{index}") for index in range(100)],
    )
    connection.commit()
    connection.close()
    write_path = RUN_DATA / "write.sqlite"
    connection = sqlite3.connect(write_path)
    connection.execute("CREATE TABLE writes(id INTEGER PRIMARY KEY,value INTEGER)")
    connection.commit()
    connection.close()
    paths["sqlite_read"] = str(read_path)
    paths["sqlite_write"] = str(write_path)
    return paths


def run_diagnostic(args: argparse.Namespace) -> dict[str, Any]:
    targets = (RESULT, EVENTS, PULSES, STATE, RUN_DATA)
    if any(path.exists() for path in targets):
        raise FileExistsError("diagnostic targets exist; refusing overwrite/retry")
    RUN_DATA.mkdir(parents=True, exist_ok=False)
    PULSES.open("x", encoding="utf-8").close()
    databases = setup_databases()
    context = mp.get_context("spawn")
    start_ns = context.Value("q", 0)
    start_event = context.Event()
    stop_event = context.Event()
    auxiliary_event = context.Event()
    ready = [context.Event() for _ in VARIANTS]
    output = context.Queue()
    args_payload = frozen_config(args)
    processes = [
        context.Process(
            target=worker,
            args=(
                variant, databases[variant], start_ns, start_event, stop_event,
                auxiliary_event, ready[index], output,
                str(RUN_DATA / f"{variant}.jsonl"), args_payload,
            ),
            name=f"handle-diagnostic-{variant}",
        )
        for index, variant in enumerate(VARIANTS)
    ]
    reports: list[dict[str, Any]] = []
    with EVENTS.open("x", encoding="utf-8", newline="\n") as events:
        for process in processes:
            process.start()
        ready_deadline = time.monotonic() + 60.0
        while not all(item.is_set() for item in ready):
            if any(process.exitcode is not None for process in processes):
                raise RuntimeError("child exited before readiness")
            if time.monotonic() >= ready_deadline:
                raise TimeoutError("child readiness timed out")
            time.sleep(0.05)
        start_ns.value = time.time_ns()
        shared.write_json(STATE, {
            "schema_version": 1,
            "started_at_ns": start_ns.value,
            "preregistered_commit": args.preregistered_commit,
            "external_start_seconds": args.warmup_seconds + args.baseline_seconds,
            "external_end_seconds": (
                args.warmup_seconds + args.baseline_seconds + args.external_seconds
            ),
        }, exclusive=True)
        append_fsynced(events, {
            "event": "run_started", "created_at": shared.utc_now(),
            "pids": [process.pid for process in processes],
        })
        start_event.set()
        print("DIAGNOSTIC_STARTED", flush=True)
        external_start = args.warmup_seconds + args.baseline_seconds
        recovery_start = external_start + args.external_seconds
        duration = recovery_start + args.recovery_seconds
        external_announced = recovery_announced = False
        try:
            while True:
                elapsed = (time.time_ns() - start_ns.value) / 1_000_000_000
                if not external_announced and elapsed >= external_start:
                    append_fsynced(events, {
                        "event": "external_phase_ready",
                        "created_at": shared.utc_now(), "elapsed_seconds": elapsed,
                    })
                    print("EXTERNAL_PHASE_READY", flush=True)
                    external_announced = True
                if not recovery_announced and elapsed >= recovery_start:
                    append_fsynced(events, {
                        "event": "recovery_phase_started",
                        "created_at": shared.utc_now(), "elapsed_seconds": elapsed,
                    })
                    print("RECOVERY_PHASE_STARTED", flush=True)
                    recovery_announced = True
                failures = [
                    process for process in processes
                    if process.exitcode is not None
                ]
                if failures:
                    raise RuntimeError(
                        f"child exited early: "
                        f"{[(item.pid, item.exitcode) for item in failures]}"
                    )
                if elapsed >= duration:
                    break
                time.sleep(0.05)
        finally:
            stop_event.set()
            for process in processes:
                process.join(timeout=30.0)
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=10.0)
        for _ in processes:
            try:
                reports.append(output.get(timeout=5.0))
            except queue.Empty:
                break
        exitcodes = [process.exitcode for process in processes]
        append_fsynced(events, {
            "event": "workers_stopped", "created_at": shared.utc_now(),
            "exitcodes": exitcodes, "reports": reports,
        })
    samples_by_variant = {
        variant: [
            json.loads(line)
            for line in (RUN_DATA / f"{variant}.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        for variant in VARIANTS
    }
    pulses = [
        json.loads(line) for line in PULSES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    analysis = analyze(samples_by_variant, pulses, reports, exitcodes, args)
    artifacts = {
        display_path(path): {"bytes": path.stat().st_size,
                             "sha256": sha256_file(path)}
        for path in [
            EVENTS, PULSES,
            *[RUN_DATA / f"{variant}.jsonl" for variant in VARIANTS],
        ]
    }
    for process in processes:
        process.close()
    output.close()
    output.join_thread()
    return {
        "schema_version": 1,
        "benchmark": "child_handle_observer_effect_diagnostic",
        "status": "PASS" if analysis["valid"] else "ERROR",
        "created_at": shared.utc_now(),
        "preregistered_commit": args.preregistered_commit,
        "config": frozen_config(args),
        "analysis": analysis,
        "reports": reports,
        "exitcodes": exitcodes,
        "artifacts": artifacts,
        "claim_boundary": (
            "Environment attribution diagnostic only; never storage, HNG, "
            "recovery, production, or v2 qualification evidence."
        ),
    }


def emit_pulse(args: argparse.Namespace) -> int:
    if not STATE.is_file() or RESULT.exists():
        raise RuntimeError("no active diagnostic accepts pulses")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if state["preregistered_commit"] != args.preregistered_commit:
        raise RuntimeError("pulse commit mismatch")
    now_ns = time.time_ns()
    elapsed = (now_ns - int(state["started_at_ns"])) / 1_000_000_000
    payload = {
        "created_at_ns": now_ns,
        "elapsed_seconds": elapsed,
        "ordinal": args.pulse_ordinal,
        "pid": os.getpid(),
        "parent_pid": os.getppid(),
        "preregistered_commit": args.preregistered_commit,
    }
    data = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(PULSES, os.O_APPEND | os.O_WRONLY)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(json.dumps(payload, sort_keys=True))
    return 0


def execute(args: argparse.Namespace) -> dict[str, Any]:
    if shared.psutil is None or not hasattr(
        shared.psutil.Process(), "num_handles"
    ):
        raise RuntimeError("Windows psutil num_handles is required")
    if not PREPARED.is_file():
        raise FileNotFoundError(PREPARED)
    head = shared.git("rev-parse", "HEAD")
    if head != args.preregistered_commit:
        raise RuntimeError("HEAD does not match preregistered commit")
    if shared.git("rev-parse", "origin/main") != head:
        raise RuntimeError("origin/main does not match preregistered HEAD")
    status = shared.git("status", "--porcelain", "--untracked-files=all")
    if status:
        raise RuntimeError(f"execution requires a clean worktree: {status}")
    payload = json.loads(PREPARED.read_text(encoding="utf-8"))
    verify_prepared(payload, args)
    return run_diagnostic(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--preregistered-commit")
    parser.add_argument("--pulse-ordinal", type=int)
    parser.add_argument("--warmup-seconds", type=float, default=30.0)
    parser.add_argument("--baseline-seconds", type=float, default=120.0)
    parser.add_argument("--external-seconds", type=float, default=120.0)
    parser.add_argument("--recovery-seconds", type=float, default=120.0)
    parser.add_argument("--sample-interval-seconds", type=float, default=1.0)
    parser.add_argument("--expected-pulses", type=int, default=20)
    parser.add_argument("--minimum-samples-per-phase", type=int, default=100)
    parser.add_argument(
        "--support-slope-margin-handles-per-minute", type=float, default=20.0
    )
    parser.add_argument(
        "--support-minimum-external-net-handles", type=int, default=50
    )
    parser.add_argument(
        "--refute-slope-tolerance-handles-per-minute", type=float, default=5.0
    )
    parser.add_argument(
        "--refute-maximum-external-net-handles", type=int, default=20
    )
    args = parser.parse_args()
    modes = [args.prepare_only, args.pulse_ordinal is not None,
             bool(args.preregistered_commit and args.pulse_ordinal is None)]
    if sum(bool(item) for item in modes) != 1:
        parser.error("select exactly one of prepare, main execution, or pulse")
    if args.pulse_ordinal is not None and not args.preregistered_commit:
        parser.error("pulse requires --preregistered-commit")
    if args.pulse_ordinal is not None and args.pulse_ordinal <= 0:
        parser.error("pulse ordinal must be positive")
    positive = (
        args.warmup_seconds, args.baseline_seconds, args.external_seconds,
        args.recovery_seconds, args.sample_interval_seconds,
        args.expected_pulses, args.minimum_samples_per_phase,
    )
    if any(value <= 0 for value in positive):
        parser.error("durations, intervals, and counts must be positive")
    return args


def main() -> int:
    mp.freeze_support()
    args = parse_args()
    if args.prepare_only:
        if PREPARED.exists():
            raise FileExistsError(f"refusing to overwrite {PREPARED}")
        payload = prepared_payload(args)
        shared.write_json(PREPARED, payload, exclusive=True)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.pulse_ordinal is not None:
        return emit_pulse(args)
    try:
        result = execute(args)
    except BaseException as exc:
        result = {
            "schema_version": 1,
            "benchmark": "child_handle_observer_effect_diagnostic",
            "status": "ERROR",
            "created_at": shared.utc_now(),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "preregistered_commit": args.preregistered_commit,
        }
        if not RESULT.exists():
            shared.write_json(RESULT, result, exclusive=True)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    shared.write_json(RESULT, result, exclusive=True)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
