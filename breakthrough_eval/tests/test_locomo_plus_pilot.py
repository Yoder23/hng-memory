from __future__ import annotations

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
