# Real HDC assistant ablation

## Status: BLOCKED_EXTERNAL

No qualifying HNG-off/on result exists. The workspace does not contain:

- a trained production HDC semantic interpreter checkpoint;
- the production assistant loop integrated with HNG 0.7;
- a frozen action library and reasoning/tool policy;
- real long-horizon interaction traces or an executable workload;
- a known-good HNG-off configuration of that same assistant.

`C:/Python310/trainslm` contains prototypes, not a usable trained production system. Synthetic
vectors, benchmark-specific encoders, or the shipped HNG integration probes cannot substitute for
the actual assistant under the program's integrity rules.

The required design is paired: same interpreter, dimensions, actions, reasoning, tools, state
logic, and workload, changing only memory. Until those resources exist, Gate 1 (real behavioral
improvement), Gate 5 (model independence), and the program's second-most-important experiment are
unmet. No effect size, confidence interval, or positive/negative conclusion about the real HDC
assistant is claimed.
