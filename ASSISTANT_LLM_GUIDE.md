# LLM assistant integration

HNG is external memory/control, not the language model. Use the same model and task prompt with or without HNG when evaluating behavioral effect.

## Bounded context

```python
from hngfrontier import HNGMemory, LLMAssistantAdapter

memory = HNGMemory("./memory", semantic_backend="faiss-auto")
adapter = LLMAssistantAdapter(memory, max_context_chars=8_000)

context = adapter.context(
    conversation_id="chat-19",
    query=encoded_semantic_state,
    lexical_query=user_message,
)
response = llm.generate(system_prompt + "\n\n" + context + "\n\n" + user_message)
```

The rendered frame includes current state, confirmed/uncertain perspective, open loops, constraints, supporting evidence, contradicting evidence, excluded/superseded items, source IDs, decision, and reasons. It does not dump arbitrary top-k chat history.

## Action advisory

```python
frame = memory.evaluate_action(
    current_state,
    proposed_action,
    conversation_id="chat-19",
    lexical_query="restart the production database",
)

if frame.assessment.decision.value == "challenge":
    # Initially give the model the challenge as advisory evidence.
    prompt_context = frame.to_prompt_context()
```

Do not hard-block by default. Log the assistant's actual action and observed outcome with `GovernedShadowEvaluator`, then calibrate on task success, action regret, stale advice, unsupported recommendations, profile violations, and abstention rate.

## Semantic inputs

LLM systems may use:

- dense `SemanticValue` fields;
- HDC projections;
- structured state/version values;
- lexical text through BM25;
- any combination with named fields.

The control plane is representation-independent. Required-state contracts still apply: an embedding does not substitute for a missing environment version or role assertion.

## Profile handling

Put known identity, permissions, role, and authority in structured `PerspectiveField` values with source and confidence. Use embeddings/HDC only for genuinely fuzzy expertise, interests, or style. An inferred profile should remain visible as uncertain and must not silently become an authorization fact.

## Evaluation gate

This RC has no common-LLM A/B result. Before production, freeze one model, prompt, encoder, dataset, and evidence budget, then compare no memory, ordinary hybrid RAG, structured memory, and HNG-governed RAG. Retrieval quality alone is not downstream success.

