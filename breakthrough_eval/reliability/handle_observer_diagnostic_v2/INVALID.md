# Invalid timing-corrected diagnostic execution

The one exact execution from preregistered commit
`8585905e7c78107228a2e93ce3987974845f0397` is **INVALID** and is not retried.
Every child, sample, report, exit-code, error, and ordinal validity control
passed except pulse timing. External process-start/approval overhead delayed the
first pulse until 180.702 seconds and made each nominal two-second cadence take
about 5.3 seconds. Pulses 18 through 20 arrived at 273.536, 279.255, and
284.688 seconds, outside the frozen `[150,270)` phase.

The fail-closed result is `status=ERROR`, `analysis.valid=false`, and
`outcome=INVALID`. All variants again showed zero external-phase handle growth,
but the failed timing control prohibits the preregistered inference. A new
protocol must widen the external window and remove intentional inter-pulse
delay; these outputs cannot be overwritten.
