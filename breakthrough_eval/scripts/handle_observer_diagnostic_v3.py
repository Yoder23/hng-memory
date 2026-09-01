#!/usr/bin/env python3
"""Timing-robust wrapper for the preregistered observer diagnostic."""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from breakthrough_eval.scripts import handle_observer_diagnostic as base  # noqa: E402


OUTPUT_DIR = (
    ROOT / "breakthrough_eval" / "reliability" /
    "handle_observer_diagnostic_v3"
)
PROTOCOL = OUTPUT_DIR / "PROTOCOL.md"
PREPARED = OUTPUT_DIR / "PREPARED.json"
RESULT = OUTPUT_DIR / "RESULTS.json"
EVENTS = OUTPUT_DIR / "events.jsonl"
PULSES = OUTPUT_DIR / "pulses.jsonl"
STATE = OUTPUT_DIR / "main_state.json"
RUN_DATA = OUTPUT_DIR / "run_data"
WRAPPER = Path(__file__).resolve()
BASE_WRAPPER = base.WRAPPER
PREDECESSOR_RESULT = (
    ROOT / "breakthrough_eval" / "reliability" /
    "handle_observer_diagnostic_v2" / "RESULTS.json"
)


def configure() -> None:
    base.OUTPUT_DIR = OUTPUT_DIR
    base.PROTOCOL = PROTOCOL
    base.PREPARED = PREPARED
    base.RESULT = RESULT
    base.EVENTS = EVENTS
    base.PULSES = PULSES
    base.STATE = STATE
    base.RUN_DATA = RUN_DATA
    base.WRAPPER = WRAPPER
    base.V2_FAILURE = PREDECESSOR_RESULT
    base.SOURCE_FILES = (
        PROTOCOL, WRAPPER, BASE_WRAPPER, PREDECESSOR_RESULT,
    )


def freeze_external_duration() -> None:
    if not any(
        value == "--external-seconds"
        or value.startswith("--external-seconds=")
        for value in sys.argv
    ):
        sys.argv.extend(["--external-seconds", "180"])


def main() -> int:
    configure()
    freeze_external_duration()
    return base.main()


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
