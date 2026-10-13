# Future Reference — OS Differential Regression Tester v0.5

## Purpose

Compare one unchanged mobile app build against two OS identities and detect candidate-OS UI, navigation, behavior and timing regressions.

## Preferred production mode

Use `market-run` with the exact same store version/build already installed on two physical devices.

## Sign-off invariants

A run is not eligible for automated compatibility sign-off unless all are true:

1. Provenance/environment gate passes.
2. Baseline execution is valid.
3. Automatic coverage is `COMPLETE_WITHIN_POLICY`.
4. Branch reset isolation is deterministic when more than one path is explored.
5. Hierarchy capture/parsing is valid.
6. No High/Critical regression is present.

`PARTIAL` coverage is reported as `INVALID`, never as PASS.

## Android real-device reset

`marketMode.androidResetStrategy = android_clear_data` is the default. It uses `adb shell pm clear <package>` between branches. The Google Play-installed package remains installed; only app data/permissions are reset.

## iOS real-device reset

A generic App Store app-data reset is not available through public XCUITest APIs. Default relaunch-only branch isolation is therefore non-deterministic. Branched iOS automatic discovery remains `PARTIAL` unless `marketMode.iosResetCommand` supplies a deterministic reset hook.

## Coverage blockers

- baseline replay failure;
- blocked destructive action;
- missing test input;
- action truncation;
- crawler depth/screen/path limit;
- non-deterministic branch reset.

## Safety

Deny rules always win. Examples such as `Continue to Pay` and `Continue to Print` remain blocked. Unknown external apps stop a path; explicitly allowed Android/iOS system UI may be captured.

## Privacy

POSIX run directories are `0700`; files are `0600`. Test credential values are redacted from XML. Persisted device IDs are masked/hashed. Configure `artifactPrivacy.sensitiveRegions` to black out sensitive screenshot areas. Set `artifactPrivacy.retentionDays` > 0 for automatic cleanup of old run directories.

## Doctor commands

```bash
./scripts/osdiff.sh doctor --mode market --platform android
./scripts/osdiff.sh doctor --mode market --platform ios
./scripts/osdiff.sh doctor --mode virtual --platform android
```

## Exit codes

```text
0   valid complete comparison, no High/Critical regression
1   setup/tool/configuration error
2   valid complete comparison with High/Critical regression
3   invalid/incomplete/partial comparison
130 cancelled
```

## INSTAX guidance

Keep safe mode on for normal automatic crawling. Print/reprint/firmware/reset/payment side effects should remain blocked and be covered by explicit controlled hardware scenarios.


## Hardware-state safety

Automatic safe mode blocks **Pair / Connect / Bluetooth / Print / Reprint / Firmware** actions by default. App-state reset does not reset external printer or Bluetooth hardware state. Use explicit controlled hardware scenarios for these flows; otherwise the automatic coverage result remains partial.
