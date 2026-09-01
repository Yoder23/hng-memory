# Real HDC assistant ablation

## Status: BLOCKED_EXTERNAL

No qualifying HNG-off/on result exists. The workspace does not contain:

- a trained production HDC semantic interpreter checkpoint;
- the production assistant loop integrated with HNG 0.7;
- a frozen action library and reasoning/tool policy;
- real long-horizon interaction traces or an executable workload;
- a known-good HNG-off configuration of that same assistant.

This boundary is now executable rather than narrative-only:

    C:\Python310\python.exe breakthrough_eval\scripts\reproduce.py real-hdc

The current invocation writes `real_hdc/READINESS.json` and fails closed with
`BLOCKED_EXTERNAL`. A future invocation may pass `--manifest PATH`. Readiness requires full
SHA-256 declarations for the interpreter, checkpoint, action library, workload traces, HNG-off
and HNG-on configurations, preregistration, and runner. It also requires affirmative paired-design
attestations that the interpreter, checkpoint, actions, reasoning policy, tools, tasks, and
retrieval candidates are identical and that only memory governance changes.

Passing this gate would authorize a paired execution; it would not itself be behavioral evidence.
The verifier confirms declared local artifacts and hashes, not whether a trace genuinely came from
real users or a production assistant. That provenance still requires independent review.

`C:/Python310/trainslm` contains prototypes, not a usable trained production system. Synthetic
vectors, benchmark-specific encoders, or the shipped HNG integration probes cannot substitute for
the actual assistant under the program's integrity rules.

The required design is paired: same interpreter, dimensions, actions, reasoning, tools, state
logic, and workload, changing only memory. Until those resources exist, Gate 1 (real behavioral
improvement), Gate 5 (model independence), and the program's second-most-important experiment are
unmet. No effect size, confidence interval, or positive/negative conclusion about the real HDC
assistant is claimed.
