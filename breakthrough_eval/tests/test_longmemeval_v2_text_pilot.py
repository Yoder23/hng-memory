from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "breakthrough_eval" / "scripts" / "longmemeval_v2_text_pilot.py"
SPEC = importlib.util.spec_from_file_location("longmemeval_v2_text_pilot", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
pilot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pilot
SPEC.loader.exec_module(pilot)


def _question(question_id: str, domain: str, question_type: str, evaluator: str):
    return {
        "id": question_id,
        "domain": domain,
        "environment": "fixture",
        "question_type": question_type,
        "question": f"question {question_id}",
        "answer": f"secret answer {question_id}",
        "eval_function": evaluator,
    }


def test_selection_is_stable_and_stratified_without_answer_dependency():
    rows = [
        _question("a", "web", "static-environment", "norm_phrase_set_match"),
        _question("b", "web", "static-environment", "norm_phrase_set_match"),
        _question("c", "web", "static-environment", "norm_phrase_set_match"),
        _question("d", "enterprise", "procedure-abs", "llm_abstention_checker"),
        _question("e", "enterprise", "procedure-abs", "llm_abstention_checker"),
    ]
    first = pilot.select_questions(rows, per_stratum=2)
    changed_answers = [{**row, "answer": "different"} for row in rows]
    second = pilot.select_questions(changed_answers, per_stratum=2)
    assert [row["id"] for row in first] == [row["id"] for row in second]
    assert len([row for row in first if row["domain"] == "web"]) == 2
    assert len([row for row in first if row["domain"] == "enterprise"]) == 1


def test_bm25_prefers_matching_state_and_respects_budget():
    candidates = [
        pilot.Candidate("a:0", "a:0", "a", 0, "unrelated weather information"),
        pilot.Candidate("b:0", "b:0", "b", 0, "incident portal filter incident mobile"),
    ]
    ranked = pilot.bm25_rank("which incident filter is available", candidates)
    assert ranked[0].candidate_id == "b:0"
    selected = pilot.select_context(ranked, top_k=1, char_budget=10)
    assert len(selected) == 1
    assert len(selected[0].text) == 10


def test_clean_fixed_candidates_render_identically_for_strong_and_hng():
    candidates = [
        pilot.Candidate("t:0", "t:0", "t", 0, "first evidence", 2.0),
        pilot.Candidate("t:1", "t:1", "t", 1, "second evidence", 1.0),
    ]
    strong, strong_trace = pilot.strong_structured_govern(candidates)
    hng, hng_trace = pilot.hng_govern(candidates)
    assert [item.candidate_id for item in strong] == [item.candidate_id for item in candidates]
    assert [item.candidate_id for item in hng] == [item.candidate_id for item in candidates]
    assert pilot.reader_messages("question", strong) == pilot.reader_messages("question", hng)
    assert not strong_trace["excluded"]
    assert not hng_trace["excluded"]


def test_candidate_corpus_does_not_consume_question_answer_or_evidence():
    trajectory = {
        "id": "t",
        "goal": "find incident",
        "outcome": "success",
        "environment": "workarena",
        "states": [{
            "state_index": 0,
            "url": "https://example.invalid",
            "action": "click('1')",
            "thought": "open the record",
            "accessibility_tree": "StaticText 'Incident'",
        }],
    }
    corpus = pilot.candidate_corpus(["t"], {"t": trajectory}, max_state_chars=500)
    assert len(corpus) == 1
    assert "find incident" in corpus[0].text
    assert "StaticText 'Incident'" in corpus[0].text
