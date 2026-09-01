# Child-handle observer diagnostic v3 protocol

Status before execution: **PREPARED_NOT_EXECUTED**.

This is a new timing-robust diagnostic, not a retry of either preserved invalid
predecessor. V1 missed its final two pulse times; v2 missed its final three
because separately approved process launches took about 5.3 seconds each. The
descriptive zero-growth observations from those invalid runs remain excluded
from the frozen decision.

## Frozen design and timing correction

The four self-sampling variants, 30-second warmup, 120-second quiet baseline,
one-second sampling, 120-second quiet recovery, exact 20 pulse ordinals,
validity checks, and decision thresholds are unchanged.

V3 widens the external-command phase from 120 to **180 seconds**, so its exact
window is `[150,330)`, and removes all intentional inter-pulse sleep. Pulses are
still separate and serial: launch ordinal N+1 immediately after ordinal N exits.
Given the two observed predecessor schedules, this leaves more than 40 seconds
of margin even if the first pulse is delayed to 181 seconds and each launch
takes six seconds.

Total self-sampling duration is 450 seconds. After the 20th pulse the operator
uses no observation command until after that duration.

## Frozen decision

- `SUPPORTS_OBSERVER_EFFECT`: valid run, median external handle slope at least
  20 handles/minute above both quiet phases, and median external net growth at
  least 50 handles.
- `REFUTES_OBSERVER_EFFECT_AT_THRESHOLD`: valid run, external slope within 5
  handles/minute of baseline, and median external net growth below 20 handles.
- otherwise: `INCONCLUSIVE`; any invalid control is `ERROR/INVALID`.

This is only an environment-attribution diagnostic. It cannot qualify HNG,
storage, recovery, production behavior, or the failed sustained v2 run.

## Execution

The wrapper freezes the 180-second external phase as its default.

```powershell
C:\Python310\python.exe breakthrough_eval\scripts\handle_observer_diagnostic_v3.py --prepare-only
C:\Python310\python.exe breakthrough_eval\scripts\handle_observer_diagnostic_v3.py --preregistered-commit COMMIT
C:\Python310\python.exe breakthrough_eval\scripts\handle_observer_diagnostic_v3.py --pulse-ordinal N --preregistered-commit COMMIT
```

Outputs are exclusive. Any further correction would require another directory,
protocol, preparation artifact, pushed commit, and execution.
