# Invalid diagnostic execution

The one exact execution from preregistered commit
`d9ff16b7257446af53d19eed873f34670e03e0aa` is **INVALID** and is not retried.
All four children completed, every exit code was zero, every measured phase had
the required samples, and ordinals 1 through 20 were recorded exactly once.
However, pulses 19 and 20 arrived at 271.357 and 276.805 seconds, after the
frozen external-command phase ended at 270 seconds. The wrapper therefore
wrote `status=ERROR`, `analysis.valid=false`, and `outcome=INVALID`.

All four child variants showed zero net handle growth during the measured
external phase even though 18 pulses fell inside it. That observation is not
admitted for the preregistered support/refutation decision because the exact
pulse-timing control failed. A valid follow-up requires a new directory,
protocol, preparation artifact, pushed commit, and more conservative pulse
cadence.

`RESULTS.json`, `events.jsonl`, `pulses.jsonl`, `main_state.json`, and the four
self-sampled child logs are preserved unchanged.
