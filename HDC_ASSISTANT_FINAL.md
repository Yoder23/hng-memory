# HDC assistant integration

`HDCAssistantAdapter` has no LLM or embedding dependency. The encoder receives exact prior semantic heads, the complete deterministic working state, recent exact turns, corrections, commitments, episode, goal, facts, constraints, effective perspective, supporting/challenging/superseded evidence, and the governed decision/frame. Immediate state carry never invokes ANN.

Run the complete loop:

```powershell
$env:PYTHONPATH="baseline_source/hng-frontier-0.5.1a1/src"
python baseline_source/hng-frontier-0.5.1a1/examples/complete_hdc_assistant.py
```

The final native HDC A/B uses the same interpreter geometry and 4,096-action library. Current-turn-only routing scored 0.78125% on ambiguous continuity versus 100% with exact HNG carry; raw HDC family routing scored 7.8125% exact top-1 versus 100% with transition memory. This is a deterministic synthetic assistant, not evidence of general natural-language understanding.

