# Child-handle observer diagnostic v2 protocol

Status before execution: **PREPARED_NOT_EXECUTED**.

This is a new timing-corrected diagnostic, not a retry or overwrite of
`../handle_observer_diagnostic`. The predecessor is preserved as `INVALID`
because pulses 19 and 20 missed its frozen external window. Neither diagnostic
can change the failed sustained-reliability v2 verdict or qualify HNG.

The scientific design, variants, phase lengths, samples, validity checks, and
decision thresholds are identical to the predecessor. The output directory,
wrapper, preparation artifact, commit, and pulse cadence are new.

## Timing correction

After `EXTERNAL_PHASE_READY`, launch exactly 20 separate serial pulse commands
approximately **two seconds apart**. The predecessor's approximately five-
second cadence plus command startup overhead placed its final two pulses after
the 120-second window. The shorter cadence targets completion in the first half
of the external phase and leaves at least 40 seconds of timing margin.

The main process still enforces exact unique ordinals 1 through 20 and requires
every pulse elapsed time in `[150,270)`. It also requires all four child reports,
zero exit failures, zero child errors, and at least 100 self-samples per child in
each baseline, external, and recovery phase.

## Frozen decision

- `SUPPORTS_OBSERVER_EFFECT`: valid run, median external handle slope at least
  20 handles/minute above both quiet phases, and median external net growth at
  least 50 handles.
- `REFUTES_OBSERVER_EFFECT_AT_THRESHOLD`: valid run, external slope within 5
  handles/minute of baseline, and median external net growth below 20 handles.
- otherwise: `INCONCLUSIVE`; any failed validity control is `ERROR/INVALID`.

## Execution

```powershell
C:\Python310\python.exe breakthrough_eval\scripts\handle_observer_diagnostic_v2.py --prepare-only
C:\Python310\python.exe breakthrough_eval\scripts\handle_observer_diagnostic_v2.py --preregistered-commit COMMIT
C:\Python310\python.exe breakthrough_eval\scripts\handle_observer_diagnostic_v2.py --pulse-ordinal N --preregistered-commit COMMIT
```

The operator makes one wait call across warmup/baseline, launches pulses at the
new cadence, then uses no observation command until after the 390-second main
duration. Outputs are exclusive and cannot be retried or overwritten.
