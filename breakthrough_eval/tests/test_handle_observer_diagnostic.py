from __future__ import annotations

import argparse
import json
from pathlib import Path
import threading
import time

import pytest

from breakthrough_eval.scripts import handle_observer_diagnostic as diagnostic
from breakthrough_eval.scripts import handle_observer_diagnostic_v2 as diagnostic_v2
from breakthrough_eval.scripts import handle_observer_diagnostic_v3 as diagnostic_v3


def qualifying_args() -> argparse.Namespace:
    return argparse.Namespace(
        preregistered_commit="commit",
        warmup_seconds=30.0,
        baseline_seconds=120.0,
        external_seconds=120.0,
        recovery_seconds=120.0,
        sample_interval_seconds=1.0,
        expected_pulses=20,
        minimum_samples_per_phase=100,
        support_slope_margin_handles_per_minute=20.0,
        support_minimum_external_net_handles=50,
        refute_slope_tolerance_handles_per_minute=5.0,
        refute_maximum_external_net_handles=20,
    )


def samples(external_growth: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for phase, start, first, growth in (
        ("baseline", 30.0, 100, 0),
        ("external", 150.0, 100, external_growth),
        ("recovery", 270.0, 100 + external_growth, 0),
    ):
        for index in range(101):
            rows.append({
                "phase": phase,
                "elapsed_seconds": start + index,
                "handles": first + round(growth * index / 100),
            })
    return rows


def pulses() -> list[dict[str, object]]:
    return [
        {"ordinal": ordinal, "elapsed_seconds": 151.0 + ordinal * 5.0}
        for ordinal in range(1, 21)
    ]


def reports() -> list[dict[str, object]]:
    return [
        {"variant": variant, "error": None}
        for variant in diagnostic.VARIANTS
    ]


def test_preparation_freezes_attribution_only_contract() -> None:
    payload = diagnostic.prepared_payload(qualifying_args())

    assert payload["status"] == "PREPARED_NOT_EXECUTED"
    assert payload["hypothesis_status_before_execution"] == "UNPROVEN"
    assert payload["config"]["expected_pulses"] == 20
    assert payload["config"]["variants"] == list(diagnostic.VARIANTS)
    assert set(payload["source_sha256"]) == {
        "breakthrough_eval/reliability/handle_observer_diagnostic/PROTOCOL.md",
        "breakthrough_eval/scripts/handle_observer_diagnostic.py",
        "breakthrough_eval/reliability/sustained_2h_v2/FAILURE_ANALYSIS.json",
    }
    assert "cannot qualify HNG" in payload["claim_boundary"]


def test_frozen_preparation_matches_current_sources() -> None:
    payload = json.loads(diagnostic.PREPARED.read_text(encoding="utf-8"))

    diagnostic.verify_prepared(payload, qualifying_args())


def test_v2_timing_correction_has_distinct_frozen_outputs() -> None:
    names = (
        "OUTPUT_DIR", "PROTOCOL", "PREPARED", "RESULT", "EVENTS",
        "PULSES", "STATE", "RUN_DATA", "WRAPPER", "V2_FAILURE",
        "SOURCE_FILES",
    )
    original = {name: getattr(diagnostic, name) for name in names}
    try:
        diagnostic_v2.configure()
        payload = json.loads(
            diagnostic_v2.PREPARED.read_text(encoding="utf-8")
        )
        diagnostic.verify_prepared(payload, qualifying_args())
        assert diagnostic.OUTPUT_DIR == diagnostic_v2.OUTPUT_DIR
        assert diagnostic.OUTPUT_DIR != original["OUTPUT_DIR"]
        assert set(payload["source_sha256"]) == {
            "breakthrough_eval/reliability/handle_observer_diagnostic/RESULTS.json",
            "breakthrough_eval/reliability/handle_observer_diagnostic_v2/PROTOCOL.md",
            "breakthrough_eval/scripts/handle_observer_diagnostic.py",
            "breakthrough_eval/scripts/handle_observer_diagnostic_v2.py",
        }
    finally:
        for name, value in original.items():
            setattr(diagnostic, name, value)


def test_v3_freezes_wider_external_window_and_distinct_outputs() -> None:
    names = (
        "OUTPUT_DIR", "PROTOCOL", "PREPARED", "RESULT", "EVENTS",
        "PULSES", "STATE", "RUN_DATA", "WRAPPER", "V2_FAILURE",
        "SOURCE_FILES",
    )
    original = {name: getattr(diagnostic, name) for name in names}
    args = qualifying_args()
    args.external_seconds = 180.0
    try:
        diagnostic_v3.configure()
        payload = json.loads(
            diagnostic_v3.PREPARED.read_text(encoding="utf-8")
        )
        diagnostic.verify_prepared(payload, args)
        assert payload["config"]["external_seconds"] == 180.0
        assert diagnostic.OUTPUT_DIR == diagnostic_v3.OUTPUT_DIR
        assert diagnostic.OUTPUT_DIR not in {
            original["OUTPUT_DIR"], diagnostic_v2.OUTPUT_DIR,
        }
        assert set(payload["source_sha256"]) == {
            "breakthrough_eval/reliability/handle_observer_diagnostic_v2/RESULTS.json",
            "breakthrough_eval/reliability/handle_observer_diagnostic_v3/PROTOCOL.md",
            "breakthrough_eval/scripts/handle_observer_diagnostic.py",
            "breakthrough_eval/scripts/handle_observer_diagnostic_v3.py",
        }
    finally:
        for name, value in original.items():
            setattr(diagnostic, name, value)


def test_phase_boundaries_are_exact() -> None:
    args = qualifying_args()

    assert diagnostic.phase_for_elapsed(29.999, args) == "warmup"
    assert diagnostic.phase_for_elapsed(30.0, args) == "baseline"
    assert diagnostic.phase_for_elapsed(149.999, args) == "baseline"
    assert diagnostic.phase_for_elapsed(150.0, args) == "external"
    assert diagnostic.phase_for_elapsed(269.999, args) == "external"
    assert diagnostic.phase_for_elapsed(270.0, args) == "recovery"


def test_frozen_support_rule_requires_external_phase_separation() -> None:
    by_variant = {
        variant: samples(external_growth=100)
        for variant in diagnostic.VARIANTS
    }

    result = diagnostic.analyze(
        by_variant, pulses(), reports(), [0, 0, 0, 0], qualifying_args()
    )

    assert result["valid"] is True
    assert result["outcome"] == "SUPPORTS_OBSERVER_EFFECT"
    assert result["median_external_net_handles"] == 100


def test_frozen_refutation_rule_and_invalid_pulse_control() -> None:
    by_variant = {
        variant: samples(external_growth=0)
        for variant in diagnostic.VARIANTS
    }
    args = qualifying_args()

    refuted = diagnostic.analyze(
        by_variant, pulses(), reports(), [0, 0, 0, 0], args
    )
    invalid = diagnostic.analyze(
        by_variant, pulses()[:-1], reports(), [0, 0, 0, 0], args
    )

    assert refuted["outcome"] == "REFUTES_OBSERVER_EFFECT_AT_THRESHOLD"
    assert invalid["valid"] is False
    assert invalid["outcome"] == "INVALID"


@pytest.mark.skipif(
    diagnostic.shared.psutil is None
    or not hasattr(diagnostic.shared.psutil.Process(), "num_handles"),
    reason="Windows psutil num_handles is required",
)
def test_multiprocess_diagnostic_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "observer"
    monkeypatch.setattr(diagnostic, "OUTPUT_DIR", output)
    monkeypatch.setattr(diagnostic, "RESULT", output / "RESULTS.json")
    monkeypatch.setattr(diagnostic, "EVENTS", output / "events.jsonl")
    monkeypatch.setattr(diagnostic, "PULSES", output / "pulses.jsonl")
    monkeypatch.setattr(diagnostic, "STATE", output / "main_state.json")
    monkeypatch.setattr(diagnostic, "RUN_DATA", output / "run_data")
    args = qualifying_args()
    args.warmup_seconds = 0.5
    args.baseline_seconds = 2.0
    args.external_seconds = 2.0
    args.recovery_seconds = 2.0
    args.sample_interval_seconds = 0.2
    args.expected_pulses = 2
    args.minimum_samples_per_phase = 5

    def emit() -> None:
        while not diagnostic.STATE.exists():
            time.sleep(0.02)
        state = json.loads(diagnostic.STATE.read_text(encoding="utf-8"))
        target = (
            int(state["started_at_ns"]) / 1_000_000_000
            + args.warmup_seconds + args.baseline_seconds + 0.2
        )
        while time.time() < target:
            time.sleep(0.02)
        for ordinal in (1, 2):
            pulse_args = argparse.Namespace(
                pulse_ordinal=ordinal,
                preregistered_commit=args.preregistered_commit,
            )
            diagnostic.emit_pulse(pulse_args)
            time.sleep(0.2)

    pulse_thread = threading.Thread(target=emit, daemon=True)
    pulse_thread.start()
    result = diagnostic.run_diagnostic(args)
    pulse_thread.join(timeout=5.0)

    assert result["status"] == "PASS"
    assert result["analysis"]["valid"] is True
    assert result["analysis"]["pulse_ordinals"] == [1, 2]
    assert result["exitcodes"] == [0, 0, 0, 0]
