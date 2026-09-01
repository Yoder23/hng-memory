#!/usr/bin/env python3
"""Corrected-output wrapper for the handle-type mechanism diagnostic."""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts import shared_sqlite_handle_diagnostic as base  # noqa: E402
from breakthrough_eval.scripts import shared_sqlite_handle_type_diagnostic as typed  # noqa: E402


OUTPUT_DIR = (
    ROOT / "breakthrough_eval" / "reliability" /
    "shared_sqlite_handle_type_diagnostic_v2"
)
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
RUN_DATA = OUTPUT_DIR / "run_data"
WRAPPER = Path(__file__).resolve()
PREDECESSOR_RESULT = typed.RESULT


def configure() -> None:
    typed.configure()
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
        typed.WRAPPER,
        typed.BASE_WRAPPER,
        typed.HANDLE_SNAPSHOT,
        typed.PREDECESSOR_RESULT,
        PREDECESSOR_RESULT,
    )


def main() -> int:
    configure()
    typed.freeze_defaults()
    return base.main()


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
