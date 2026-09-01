from __future__ import annotations

from breakthrough_eval.scripts import personamem_v2_pilot as pilot


def row(pref_type: str = "ask_to_forget") -> dict[str, str]:
    return {
        "persona_id": "7",
        "pref_type": pref_type,
        "chat_history_32k_link": "data/history.json",
        "user_query": "{'role': 'user', 'content': 'What should I choose?'}",
        "correct_answer": "correct secret",
        "incorrect_answers": '["wrong one", "wrong two", "wrong three"]',
        "preference": "oracle preference",
        "related_conversation_snippet": "oracle snippet",
        "short_persona": "oracle short profile",
        "expanded_persona": "oracle expanded profile",
        "updated": "True",
    }


def test_selection_excludes_answers_profiles_preferences_and_oracles():
    original = row()
    changed = {
        **original,
        "correct_answer": "changed",
        "incorrect_answers": '["changed"]',
        "preference": "changed",
        "related_conversation_snippet": "changed",
        "short_persona": "changed",
        "expanded_persona": "changed",
    }
    assert pilot.selection_key(4, original) == pilot.selection_key(4, changed)


def test_system_persona_is_excluded_from_retrieval_candidates():
    history = [
        {"role": "system", "content": "SECRET PERSONA"},
        {"role": "user", "content": "I like tea"},
        {"role": "assistant", "content": "Noted"},
    ]
    candidates = pilot.conversation_candidates(1, history, chunk_size=6, chunk_overlap=2)
    assert len(candidates) == 1
    assert "SECRET PERSONA" not in candidates[0].text
    assert "I like tea" in candidates[0].text


def test_options_are_deterministic_and_extract_final_letter():
    first = pilot.option_bundle(11, row())
    second = pilot.option_bundle(11, row())
    assert first == second
    assert first[1] in "ABCD"
    assert pilot.extract_letter("Reasoning. Final Answer: [C]") == "C"
    assert pilot.extract_letter(r"answer is \boxed{b}") == "B"


def test_full_history_mcq_is_the_final_user_turn():
    history = [
        {"role": "system", "content": "persona"},
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
    ]
    messages = pilot.messages_for_arm("full_history", row(), history, [], "query with A. one")
    assert messages[:-1] == history
    assert messages[-1] == {"role": "user", "content": "query with A. one"}


def test_clean_governance_arms_preserve_identical_candidates():
    history = [
        {"role": "user", "content": "I prefer quiet hotels"},
        {"role": "assistant", "content": "Understood"},
    ]
    base = pilot.conversation_candidates(2, history, chunk_size=2, chunk_overlap=0)
    strong, _ = pilot.strong_structured_govern(base)
    hng, trace = pilot.hng_govern(
        base,
        source_identity="PersonaMem-v2",
        source_id_prefix="personamem-v2",
    )
    assert [item.candidate_id for item in strong] == [item.candidate_id for item in base]
    assert [item.candidate_id for item in hng] == [item.candidate_id for item in base]
    assert trace["included"][0]["source"]["identity"] == "PersonaMem-v2"
    assert trace["included"][0]["source"]["source_id"].startswith("personamem-v2:")


def test_completed_keys_fail_closed_on_caps_and_wrong_hng_identity(tmp_path):
    raw = tmp_path / "events.jsonl"
    common = {
        "event": "prediction",
        "arm": "hng",
        "predicted_letter": "A",
        "reader": {"raw_response": {"done_reason": "stop"}},
    }
    pilot.append_jsonl(raw, {**common, "source_index": 1, "source_identity": "LongMemEval-V2"})
    pilot.append_jsonl(raw, {**common, "source_index": 2, "source_identity": "PersonaMem-v2"})
    pilot.append_jsonl(raw, {
        **common,
        "source_index": 3,
        "source_identity": "PersonaMem-v2",
        "reader": {"raw_response": {"done_reason": "length"}},
    })
    assert pilot.completed_keys(raw) == {(2, "hng")}
