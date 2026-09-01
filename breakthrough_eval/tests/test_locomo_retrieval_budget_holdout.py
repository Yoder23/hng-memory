from __future__ import annotations

import json

from breakthrough_eval.scripts import locomo_plus_pilot as pilot
from breakthrough_eval.scripts import locomo_retrieval_budget_holdout as holdout


def sample_set(per_category: int = 12):
    rows = []
    for category in pilot.CATEGORIES:
        for index in range(per_category):
            rows.append({
                "category": category,
                "input_prompt": f"prompt {category} {index}",
                "trigger": f"trigger {index}",
                "answer": f"answer {index}",
                "evidence": f"evidence {index}",
            })
    return rows


def test_holdout_window_is_disjoint_from_development_window():
    rows = sample_set()
    development = holdout.select_samples_window(rows, per_category=5, offset=0)
    held_out = holdout.select_samples_window(rows, per_category=5, offset=5)
    assert not ({index for index, _ in development} & {index for index, _ in held_out})
    assert len(held_out) == 30


def test_window_selection_ignores_answers_and_oracle_evidence():
    rows = sample_set()
    first = holdout.select_samples_window(rows, per_category=2, offset=5)
    changed = [{**row, "answer": "changed", "evidence": "changed"} for row in rows]
    second = holdout.select_samples_window(changed, per_category=2, offset=5)
    assert [index for index, _ in first] == [index for index, _ in second]


def test_inference_config_hash_changes_with_generation_budget():
    class Args:
        model = pilot.DEFAULT_MODEL
        model_digest = pilot.DEFAULT_DIGEST
        num_predict = 192

    first = holdout.inference_config_hash(Args())
    Args.num_predict = 256
    second = holdout.inference_config_hash(Args())
    assert first != second


def test_reusable_events_requires_full_inference_config(tmp_path):
    raw = tmp_path / "events.jsonl"
    row = {
        "source_index": 1, "prompt_sha256": "prompt", "inference_config_sha256": "config",
        "prediction": "x", "judge_score": 1.0, "reader": {}, "judge": {},
    }
    raw.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert (1, "prompt", "config") in holdout.reusable_events(raw)


def test_completed_keys_rejects_wrong_hng_identity(tmp_path):
    raw = tmp_path / "events.jsonl"
    invalid = {
        "event": "prediction", "source_index": 1, "arm": "hng_k64",
        "source_identity": "wrong",
    }
    valid = {
        "event": "prediction", "source_index": 2, "arm": "hng_k64",
        "source_identity": "LoCoMo-Plus",
    }
    raw.write_text(json.dumps(invalid) + "\n" + json.dumps(valid) + "\n", encoding="utf-8")
    assert holdout.completed_keys(raw) == {(2, "hng_k64")}


def test_comparison_known_tie():
    latest = {
        (1, "left"): {"judge_score": 1.0}, (1, "right"): {"judge_score": 1.0},
        (2, "left"): {"judge_score": 0.0}, (2, "right"): {"judge_score": 0.0},
    }
    result = holdout.comparison(latest, "left", "right")
    assert result["paired_bootstrap_mean_score"]["delta"] == 0.0
    assert result["mcnemar_judge_positive"]["exact_two_sided_p"] == 1.0
