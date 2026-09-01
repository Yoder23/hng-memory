from __future__ import annotations

import json

from breakthrough_eval.scripts import locomo_plus_pilot as pilot


def test_non_cognitive_question_is_removed_from_retrieval_memory():
    sample = {
        "category": "single-hop",
        "input_prompt": "DATE: today\nCONVERSATION:\nA said, \"memory\"\n\nQuestion: What happened?",
        "trigger": "What happened?",
        "answer": "memory",
        "evidence": "A: memory",
    }
    memory, query, full = pilot.split_memory_and_query(sample)
    assert query == "What happened?"
    assert "Question:" not in memory
    assert "memory" in memory
    assert full.endswith("What happened?")


def test_cognitive_trigger_is_current_query_not_retrieval_memory():
    sample = {
        "category": "Cognitive",
        "input_prompt": (
            'Caroline said, "I learned to say no to extra work."\n'
            'Caroline said, "I volunteered again and now I am overwhelmed."'
        ),
        "trigger": "A: I volunteered again and now I am overwhelmed.",
        "evidence": "Caroline: I learned to say no to extra work.",
    }
    memory, query, _full = pilot.split_memory_and_query(sample)
    assert "learned to say no" in memory
    assert "volunteered again" not in memory
    assert "volunteered again" in query


def test_selection_does_not_depend_on_answer_or_oracle_evidence():
    samples = []
    for index, category in enumerate(pilot.CATEGORIES):
        for variant in range(3):
            samples.append({
                "category": category,
                "input_prompt": f"prompt {category} {variant}",
                "trigger": f"trigger {variant}",
                "answer": f"answer {index} {variant}",
                "evidence": f"oracle {index} {variant}",
            })
    first = pilot.select_samples(samples, 1)
    changed = [{**item, "answer": "changed", "evidence": "changed"} for item in samples]
    second = pilot.select_samples(changed, 1)
    assert [index for index, _ in first] == [index for index, _ in second]
    assert {sample["category"] for _, sample in first} == set(pilot.CATEGORIES)


def test_clean_governance_arms_render_identical_retrieved_prompt():
    base = [
        pilot.Candidate("x:0", "x:0", "x", 0, "DATE: now\nA said memory", 1.0),
        pilot.Candidate("x:1", "x:1", "x", 1, "DATE: now\nB said response", 0.5),
    ]
    strong, _strong_trace = pilot.strong_structured_govern(base)
    hng, hng_trace = pilot.hng_govern(base)
    assert not hng_trace["excluded"]
    strong_body = pilot.render_retrieved(strong, "What happened?", "single-hop")
    hng_body = pilot.render_retrieved(hng, "What happened?", "single-hop")
    assert pilot.reader_messages(strong_body, "single-hop") == pilot.reader_messages(hng_body, "single-hop")


def test_protocol_label_records_actual_sample_density():
    assert "(5 per category)" in pilot.protocol_label(5)
    assert "NONCANONICAL" in pilot.protocol_label(5)


def test_paired_statistics_known_values():
    result = pilot.paired_bootstrap_delta([1.0, 1.0, 0.0], [0.0, 1.0, 0.0], samples=100)
    assert result["delta"] == 1 / 3
    exact = pilot.mcnemar([True, True, False], [False, True, False])
    assert exact["discordant"] == 1
    assert exact["exact_two_sided_p"] == 1.0


def test_reusable_predictions_requires_same_sample_prompt_and_model(tmp_path):
    raw = tmp_path / "events.jsonl"
    event = {
        "event": "prediction", "source_index": 7, "arm": "bm25",
        "prompt_sha256": "prompt", "model_digest": "model", "prediction": "answer",
        "judge_score": 1.0, "reader": {}, "judge": {}, "ground_truth": "answer",
        "oracle_judge_evidence": "evidence",
    }
    raw.write_text(json.dumps(event) + "\n", encoding="utf-8")
    cached = pilot.reusable_predictions(raw)
    assert cached[(7, "prompt", "model")]["arm"] == "bm25"
    assert (8, "prompt", "model") not in cached
