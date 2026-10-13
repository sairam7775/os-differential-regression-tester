# Automatic Discovery — v0.5

Automatic discovery is used by both virtual `auto-run` and physical `market-run`.

## Algorithm

```text
Reset to known start state
  ↓
Launch target app
  ↓
Verify foreground app/system surface
  ↓
Capture native hierarchy
  ↓
Fingerprint hierarchy + normalized text/value + foreground context
  ↓
Fill configured test inputs
  ↓
Discover tappable controls
  ↓
Apply fail-closed safety filter
  ↓
Queue child paths breadth-first
```

Each queued path is replayed from the reset start state. The candidate OS replays the paths discovered on baseline.

## Safety

Deny patterns are evaluated first and cannot be overridden by allowed words. `Continue to Pay` and `Continue to Print` are blocked in safe mode.

If a screen contains more controls than `maxActionsPerScreen`, the extra controls are recorded as `actions_truncated` and coverage becomes `PARTIAL`; they are never silently omitted from a “complete” run.

## State identity

Visible `text`/`value` is included by default and normalized using `fingerprintIgnorePatterns`. This prevents onboarding/list/detail screens with the same control structure but different visible content from being collapsed into one state.

Foreground package/activity or iOS bundle context is also part of the state identity.

## Coverage becomes PARTIAL when

- baseline path replay fails;
- app state cannot be reset deterministically for branched exploration;
- an unsafe action is blocked;
- a required input has no rule/value;
- action candidates are truncated;
- crawler limits are reached.

The report itself becomes `INVALID` for full compatibility sign-off when coverage is PARTIAL.

## Behavior/timing

The complete action trace used to reach every checkpoint is persisted on baseline and candidate. The comparison engine detects candidate action failures and configured duration regressions.


## Hardware-state safety

Automatic safe mode blocks **Pair / Connect / Bluetooth / Print / Reprint / Firmware** actions by default. App-state reset does not reset external printer or Bluetooth hardware state. Use explicit controlled hardware scenarios for these flows; otherwise the automatic coverage result remains partial.
