# Fixed-LLM memory ablation

Status: 30-case untouched synthetic holdout completed. Public and real-assistant validation remain
open.

## Frozen controls

- Model: qwen3.8:27b-q4_K_M
- Ollama manifest digest:
  25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e
- Temperature: 0
- Seed: 20260831
- Maximum generation: 32 tokens
- Declared inference context: 32,768 tokens
- Same task, state, tools, model, outer prompt template, candidate IDs/order and candidate-pool hash
- Only rendered memory context varies
- All 90 calls completed; no failed events

The holdout is variants 05–24, fixed before inference. The first 30 cases cover three variants of
all ten adversarial families.

## Downstream result

| Memory arm | Correct | Accuracy | Prompt tokens | p50 latency | p95 latency |
|---|---:|---:|---:|---:|---:|
| Ordinary candidate context | 17/30 | 56.7% | 41,046 | 6.785 s | 8.825 s |
| StrongStructuredBaseline | 27/30 | 90.0% | 16,215 | 3.976 s | 5.674 s |
| HNG | 27/30 | 90.0% | 17,103 | 3.741 s | 5.483 s |

HNG versus ordinary context:

- paired accuracy delta +33.3 percentage points;
- paired bootstrap 95% CI +16.7 to +50.0 points;
- exact McNemar: ten HNG-only correct, zero ordinary-only correct, p=0.001953125.

HNG versus StrongStructuredBaseline:

- delta 0;
- zero discordant cases;
- exact McNemar p=1.0.

## Family analysis

HNG and StrongStructuredBaseline are perfect on nine families and return conflicted on all three
duplicate-boundary cases where the frozen expectation is challenge.

Ordinary candidate context is perfect on irrelevant state, sparse verified evidence, stale
environment, supersession, and true conflict. It fails all authority-mismatch and untrusted-poison
cases, all duplicate-boundary cases, and most wrong-role/wrong-tenant cases.

## Interpretation boundary

This is downstream behavior with a fixed strong local LLM, so it supports the narrow claim that
explicit applicability governance can improve a model under synthetic corruption while reducing
context. It does not establish a public benchmark result, a real-assistant improvement, or an
HNG-specific advantage. The exact tie with the simple baseline is currently the more important
architectural result.

Raw model responses, prompt hashes, token counts and timings are in
fixed_candidate/raw/llm_events.jsonl.
