#!/usr/bin/env python3
"""Preregistered rotation/checkpoint treatment for WAL-index handle growth."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "baseline_source" / "hng-frontier-0.5.1a1" / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PACKAGE))

from breakthrough_eval.scripts import shared_sqlite_handle_diagnostic as matrix  # noqa: E402
from breakthrough_eval.scripts import shared_sqlite_handle_type_diagnostic_v3 as typed_v3  # noqa: E402
from breakthrough_eval.scripts import shared_sqlite_wal_index_diagnostic as wal_index  # noqa: E402


OUTPUT_DIR = (
    ROOT / "breakthrough_eval" / "reliability" /
    "wal_checkpoint_rotation_diagnostic"
)
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
RUN_DATA = OUTPUT_DIR / "run_data"
WRAPPER = Path(__file__).resolve()
STORAGE = PACKAGE / "hngfrontier" / "storage_v2.py"
PREDECESSOR_RESULT = wal_index.RESULT
SOURCE_FILES = (
    PROTOCOL,
    WRAPPER,
    STORAGE,
    typed_v3.WRAPPER,
    wal_index.WRAPPER,
    PREDECESSOR_RESULT,
)


def display_path(path: Path) -> str:
    return matrix.display_path(path)


def source_hashes() -> dict[str, str]:
    return {
        display_path(path): matrix.observer.sha256_file(path)
        for path in SOURCE_FILES
    }


def frozen_config(args: argparse.Namespace) -> dict[str, object]:
    return {
        "baseline_seconds": args.baseline_seconds,
        "treatment_replications": args.treatment_replications,
        "treatment_epochs": args.treatment_epochs,
        "treatment_epoch_seconds": args.treatment_epoch_seconds,
        "writer_workers": args.writer_workers,
        "reader_workers": args.reader_workers,
        "seed_records": args.seed_records,
        "tenants": args.tenants,
        "sample_interval_seconds": args.sample_interval_seconds,
        "baseline_minimum_samples_per_child": (
            args.baseline_minimum_samples_per_child
        ),
        "treatment_minimum_samples_per_child": (
            args.treatment_minimum_samples_per_child
        ),
        "baseline_minimum_shm_unit_delta": (
            args.baseline_minimum_shm_unit_delta
        ),
        "baseline_minimum_maximum_process_handles": (
            args.baseline_minimum_maximum_process_handles
        ),
        "treatment_maximum_process_handles": (
            args.treatment_maximum_process_handles
        ),
        "treatment_maximum_section_delta_per_epoch": (
            args.treatment_maximum_section_delta_per_epoch
        ),
        "maximum_post_checkpoint_wal_bytes": (
            args.maximum_post_checkpoint_wal_bytes
        ),
        "minimum_treatment_throughput_ratio": (
            args.minimum_treatment_throughput_ratio
        ),
        "checkpoint_mode": "TRUNCATE",
        "multiprocessing_start_method": "spawn",
    }


def prepared_payload(args: argparse.Namespace) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "PREPARED_NOT_EXECUTED",
        "created_at": matrix.sustained.utc_now(),
        "config": frozen_config(args),
        "source_sha256": source_hashes(),
        "predecessor_result": display_path(PREDECESSOR_RESULT),
        "qualifying_command": [
            sys.executable,
            display_path(WRAPPER),
            "--preregistered-commit",
            "COMMIT",
        ],
        "claim_boundary": (
            "Bounded reliability-intervention evidence only. It cannot make "
            "the failed sustained run pass or qualify HNG or production use."
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


def epoch_payload_config(args: argparse.Namespace) -> dict[str, object]:
    return {
        "sample_interval_seconds": args.sample_interval_seconds,
        "tenants": args.tenants,
        "seed_records": args.seed_records,
    }


def database_identity(
    store: Any, expected_generation: int,
) -> dict[str, object]:
    row_count = int(store.con.execute("SELECT COUNT(*) FROM evidence").fetchone()[0])
    generation = store.generation()
    quick_check = str(store.con.execute("PRAGMA quick_check").fetchone()[0])
    return {
        "expected_generation": expected_generation,
        "row_count": row_count,
        "generation": generation,
        "quick_check": quick_check,
        "passed": (
            row_count == expected_generation
            and generation == expected_generation
            and quick_check == "ok"
        ),
    }


def summarize_epoch(result: Mapping[str, Any]) -> dict[str, object]:
    mapping = wal_index.mapping_analysis({"epoch": result})["epoch"]
    writer_operations = sum(
        int(report["operations"])
        for report in result["reports"]
        if report["role"] == "writer"
    )
    reader_operations = sum(
        int(report["operations"])
        for report in result["reports"]
        if report["role"] == "reader"
    )
    return {
        "valid": result["valid"],
        "writer_operations": writer_operations,
        "reader_operations": reader_operations,
        "maximum_process_handles": max(
            int(child["maximum_handles"])
            for child in result["per_child"]
        ),
        "maximum_net_handles": max(
            int(child["net_handles"])
            for child in result["per_child"]
        ),
        "median_section_delta": mapping["median_section_delta"],
        "maximum_section_delta": max(
            int(report["handle_type_delta"].get("Section", 0))
            for report in result["reports"]
        ),
        "median_shm_unit_delta": mapping["median_shm_unit_delta"],
        "maximum_section_shm_delta_error": (
            mapping["maximum_absolute_delta_error"]
        ),
    }


def run_shared_epoch(
    context: Any,
    *,
    database: Path,
    run_root: Path,
    condition: str,
    condition_epoch: int,
    duration_seconds: float,
    minimum_samples: int,
    args: argparse.Namespace,
    events: Any,
) -> dict[str, Any]:
    previous_run_data = matrix.RUN_DATA
    previous_prepare = matrix.prepare_condition_databases
    previous_config = matrix.frozen_config
    matrix.RUN_DATA = run_root
    matrix.prepare_condition_databases = lambda *_args, **_kwargs: [
        str(database)
    ] * (args.writer_workers + args.reader_workers)
    matrix.frozen_config = epoch_payload_config
    epoch_args = argparse.Namespace(**vars(args))
    epoch_args.condition_seconds = duration_seconds
    epoch_args.minimum_samples_per_child = minimum_samples
    try:
        return typed_v3.queue_safe_run_condition(
            context, condition, condition_epoch, epoch_args, events
        )
    finally:
        matrix.RUN_DATA = previous_run_data
        matrix.prepare_condition_databases = previous_prepare
        matrix.frozen_config = previous_config


def checkpoint(
    store: Any, database: Path,
) -> dict[str, object]:
    started = time.perf_counter()
    row = store.con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    state = wal_index.file_state(str(database))
    return {
        "busy": int(row[0]),
        "log_frames": int(row[1]),
        "checkpointed_frames": int(row[2]),
        "duration_seconds": time.perf_counter() - started,
        "file_state": state,
        "passed": (
            int(row[0]) == 0
            and int(state["wal_bytes"] or 0)
            <= 32768
        ),
    }


def run_baseline(
    context: Any, args: argparse.Namespace, events: Any,
) -> dict[str, Any]:
    root = RUN_DATA / "baseline"
    root.mkdir(parents=True, exist_ok=False)
    database = root / "evidence.sqlite"
    matrix.seed_database(database, args.seed_records, args.tenants)
    coordinator = matrix.SQLiteEvidenceStore(database)
    try:
        result = run_shared_epoch(
            context,
            database=database,
            run_root=root / "epochs",
            condition="baseline",
            condition_epoch=0,
            duration_seconds=args.baseline_seconds,
            minimum_samples=args.baseline_minimum_samples_per_child,
            args=args,
            events=events,
        )
        summary = summarize_epoch(result)
        expected = args.seed_records + int(summary["writer_operations"])
        identity = database_identity(coordinator, expected)
    finally:
        coordinator.close()
    return {
        "result": result,
        "summary": summary,
        "identity": identity,
        "throughput_operations_per_second": (
            int(summary["writer_operations"])
            + int(summary["reader_operations"])
        ) / args.baseline_seconds,
    }


def run_treatment(
    context: Any,
    replication: int,
    args: argparse.Namespace,
    events: Any,
) -> dict[str, Any]:
    root = RUN_DATA / f"treatment-{replication:02d}"
    root.mkdir(parents=True, exist_ok=False)
    database = root / "evidence.sqlite"
    matrix.seed_database(database, args.seed_records, args.tenants)
    coordinator = matrix.SQLiteEvidenceStore(database)
    epochs = []
    total_writes = total_reads = 0
    try:
        for epoch in range(args.treatment_epochs):
            result = run_shared_epoch(
                context,
                database=database,
                run_root=root / "epochs",
                condition=f"epoch-{epoch:02d}",
                condition_epoch=replication * 100 + epoch,
                duration_seconds=args.treatment_epoch_seconds,
                minimum_samples=args.treatment_minimum_samples_per_child,
                args=args,
                events=events,
            )
            summary = summarize_epoch(result)
            cycle = checkpoint(coordinator, database)
            total_writes += int(summary["writer_operations"])
            total_reads += int(summary["reader_operations"])
            epoch_result = {
                "epoch": epoch,
                "result": result,
                "summary": summary,
                "checkpoint": cycle,
            }
            epochs.append(epoch_result)
            matrix.observer.append_fsynced(events, {
                "event": "treatment_epoch_completed",
                "created_at": matrix.sustained.utc_now(),
                "replication": replication,
                "epoch": epoch,
                "maximum_process_handles": summary[
                    "maximum_process_handles"
                ],
                "checkpoint": cycle,
            })
        identity = database_identity(
            coordinator, args.seed_records + total_writes
        )
    finally:
        coordinator.close()
    duration = args.treatment_epochs * args.treatment_epoch_seconds
    return {
        "replication": replication,
        "epochs": epochs,
        "writer_operations": total_writes,
        "reader_operations": total_reads,
        "throughput_operations_per_second": (
            total_writes + total_reads
        ) / duration,
        "identity": identity,
    }


def classify(
    baseline: Mapping[str, Any],
    treatments: list[Mapping[str, Any]],
    args: argparse.Namespace,
) -> str:
    baseline_summary = baseline["summary"]
    if (
        not baseline_summary["valid"]
        or not baseline["identity"]["passed"]
        or any(
            not treatment["identity"]["passed"]
            or any(not epoch["summary"]["valid"] for epoch in treatment["epochs"])
            for treatment in treatments
        )
    ):
        return "INVALID"
    baseline_reproduced = (
        int(baseline_summary["maximum_process_handles"])
        >= args.baseline_minimum_maximum_process_handles
        and float(baseline_summary["median_shm_unit_delta"] or 0)
        >= args.baseline_minimum_shm_unit_delta
    )
    treatment_bounded = all(
        int(epoch["summary"]["maximum_process_handles"])
        < args.treatment_maximum_process_handles
        and int(epoch["summary"]["maximum_section_delta"])
        <= args.treatment_maximum_section_delta_per_epoch
        and epoch["checkpoint"]["busy"] == 0
        and int(epoch["checkpoint"]["file_state"]["wal_bytes"] or 0)
        <= args.maximum_post_checkpoint_wal_bytes
        for treatment in treatments
        for epoch in treatment["epochs"]
    )
    throughput_retained = all(
        float(treatment["throughput_operations_per_second"])
        / float(baseline["throughput_operations_per_second"])
        >= args.minimum_treatment_throughput_ratio
        for treatment in treatments
    )
    if baseline_reproduced and treatment_bounded and throughput_retained:
        return "SUPPORTS_ROTATE_CHECKPOINT_WAL_BOUNDING"
    return "INCONCLUSIVE"


def run_diagnostic(args: argparse.Namespace) -> dict[str, Any]:
    if RESULT.exists() or EVENTS.exists() or RUN_DATA.exists():
        raise FileExistsError("diagnostic targets exist; refusing overwrite/retry")
    RUN_DATA.mkdir(parents=True, exist_ok=False)
    context = mp.get_context("spawn")
    wal_index.configure()
    with EVENTS.open("x", encoding="utf-8", newline="\n") as events:
        matrix.observer.append_fsynced(events, {
            "event": "run_started",
            "created_at": matrix.sustained.utc_now(),
            "config": frozen_config(args),
        })
        baseline = run_baseline(context, args, events)
        treatments = [
            run_treatment(context, replication, args, events)
            for replication in range(args.treatment_replications)
        ]
        outcome = classify(baseline, treatments, args)
        matrix.observer.append_fsynced(events, {
            "event": "run_completed",
            "created_at": matrix.sustained.utc_now(),
            "outcome": outcome,
        })
    valid = outcome != "INVALID"
    return {
        "schema_version": 1,
        "benchmark": "wal_checkpoint_rotation_intervention_diagnostic",
        "status": "PASS" if valid else "ERROR",
        "created_at": matrix.sustained.utc_now(),
        "config": frozen_config(args),
        "outcome": outcome,
        "baseline": baseline,
        "treatments": treatments,
        "events": {
            "path": display_path(EVENTS),
            "bytes": EVENTS.stat().st_size,
            "sha256": matrix.observer.sha256_file(EVENTS),
        },
        "claim_boundary": (
            "Bounded rotation/checkpoint intervention only; never HNG, "
            "production, or sustained-run qualification evidence."
        ),
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    if not PREPARED.is_file():
        raise FileNotFoundError(PREPARED)
    head = matrix.sustained.git("rev-parse", "HEAD")
    if head != args.preregistered_commit:
        raise RuntimeError("HEAD does not match preregistered commit")
    if matrix.sustained.git("rev-parse", "origin/main") != head:
        raise RuntimeError("origin/main does not match preregistered HEAD")
    status = matrix.sustained.git(
        "status", "--porcelain", "--untracked-files=all"
    )
    if status:
        raise RuntimeError(f"execution requires a clean worktree: {status}")
    payload = json.loads(PREPARED.read_text(encoding="utf-8"))
    verify_prepared(payload, args)
    result = run_diagnostic(args)
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
    parser.add_argument("--baseline-seconds", type=float, default=120.0)
    parser.add_argument("--treatment-replications", type=int, default=2)
    parser.add_argument("--treatment-epochs", type=int, default=4)
    parser.add_argument("--treatment-epoch-seconds", type=float, default=30.0)
    parser.add_argument("--writer-workers", type=int, default=4)
    parser.add_argument("--reader-workers", type=int, default=8)
    parser.add_argument("--seed-records", type=int, default=1000)
    parser.add_argument("--tenants", type=int, default=100)
    parser.add_argument("--sample-interval-seconds", type=float, default=1.0)
    parser.add_argument(
        "--baseline-minimum-samples-per-child", type=int, default=100
    )
    parser.add_argument(
        "--treatment-minimum-samples-per-child", type=int, default=25
    )
    parser.add_argument(
        "--baseline-minimum-shm-unit-delta", type=int, default=60
    )
    parser.add_argument(
        "--baseline-minimum-maximum-process-handles", type=int, default=300
    )
    parser.add_argument(
        "--treatment-maximum-process-handles", type=int, default=300
    )
    parser.add_argument(
        "--treatment-maximum-section-delta-per-epoch", type=int, default=40
    )
    parser.add_argument(
        "--maximum-post-checkpoint-wal-bytes", type=int, default=32768
    )
    parser.add_argument(
        "--minimum-treatment-throughput-ratio", type=float, default=0.50
    )
    args = parser.parse_args()
    if args.prepare_only == bool(args.preregistered_commit):
        parser.error("select exactly one of prepare or execution")
    positive = (
        args.baseline_seconds,
        args.treatment_replications,
        args.treatment_epochs,
        args.treatment_epoch_seconds,
        args.writer_workers,
        args.reader_workers,
        args.seed_records,
        args.tenants,
        args.sample_interval_seconds,
        args.baseline_minimum_samples_per_child,
        args.treatment_minimum_samples_per_child,
        args.baseline_minimum_shm_unit_delta,
        args.baseline_minimum_maximum_process_handles,
        args.treatment_maximum_process_handles,
        args.treatment_maximum_section_delta_per_epoch,
        args.maximum_post_checkpoint_wal_bytes,
        args.minimum_treatment_throughput_ratio,
    )
    if any(value <= 0 for value in positive):
        parser.error("all durations, counts, limits, and ratios must be positive")
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
        matrix.sustained.write_json(PREPARED, payload, exclusive=True)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    try:
        result = execute(args)
    except BaseException as exc:
        result = {
            "schema_version": 1,
            "benchmark": "wal_checkpoint_rotation_intervention_diagnostic",
            "status": "ERROR",
            "created_at": matrix.sustained.utc_now(),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "preregistered_commit": args.preregistered_commit,
        }
        if not RESULT.exists():
            matrix.sustained.write_json(RESULT, result, exclusive=True)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    matrix.sustained.write_json(RESULT, result, exclusive=True)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
