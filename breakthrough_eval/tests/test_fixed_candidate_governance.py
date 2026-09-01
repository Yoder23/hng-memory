from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "breakthrough_eval" / "scripts" / "fixed_candidate_governance.py"
SPEC = importlib.util.spec_from_file_location("fixed_candidate_governance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_generator_is_frozen_at_250_with_untouched_holdout():
    scenarios = MODULE.generate_scenarios()
    assert len(scenarios) == 250
    assert sum(case.split == "development" for case in scenarios) == 50
    assert sum(case.split == "holdout" for case in scenarios) == 200
    assert len({case.case_id for case in scenarios}) == 250


def test_repeated_stale_candidates_retain_stale_environment():
    scenario = next(
        case
        for case in MODULE.generate_scenarios()
        if case.case_id == "stale_environment-00"
    )
    stale = [
        item
        for item in scenario.candidates
        if item.source_event_id.endswith("-old")
    ]
    assert len(stale) == 5
    assert all(item.validity.environment_version == "v1" for item in stale)
    assert all(
        item.semantics.fields["environment_version"].value == "v1"
        for item in stale
    )


def test_hng_and_strong_structured_match_but_preserve_duplicate_boundary_loss():
    scenarios = MODULE.generate_scenarios()
    for scenario in scenarios:
        hng = MODULE.hng_decide(scenario)["decision"]
        strong = MODULE.strong_structured_decide(scenario)["decision"]
        assert hng == strong
    duplicate = next(case for case in scenarios if case.case_id == "duplicate_attack-00")
    assert duplicate.expected == "challenge"
    assert MODULE.hng_decide(duplicate)["decision"] == "conflicted"


def test_mcnemar_exact_known_values():
    result = MODULE.mcnemar([True] * 10, [False] * 10)
    assert result["discordant"] == 10
    assert result["left_correct_right_wrong"] == 10
    assert result["right_correct_left_wrong"] == 0
    assert result["exact_two_sided_p"] == 0.001953125


def test_ollama_decision_outside_frozen_enum_fails_closed(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"message": {"content": '{"decision":"invented"}'}}).encode()

    monkeypatch.setattr(MODULE.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    scenario = next(case for case in MODULE.generate_scenarios() if case.split == "development")
    context = MODULE.context_for("ordinary_rag", scenario, MODULE.raw_majority_decide(scenario))
    with pytest.raises(ValueError, match="unsupported model decision"):
        MODULE.ollama_decide(
            "test-model", scenario, context, endpoint="http://unused", timeout=1.0
        )
