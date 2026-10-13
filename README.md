# OS Differential Regression Tester — v0.5 Hardened

A standalone local regression tool for comparing the **same mobile app build** across an old/stable OS and a new/candidate OS. The production-oriented workflow uses the **market-installed app on two physical devices** and automatically discovers/replays reachable UI states.

## Development baseline

See [the v0.5.0 baseline assessment](docs/BASELINE_ASSESSMENT.md) for actual test results, known safety and validity issues, and the prioritized stabilization plan. The imported baseline has not been validated on physical devices.

## Primary workflow: `market-run`

The app must already be installed from Google Play or Apple App Store. The tool does **not** sideload, replace, upgrade, or downgrade the app under test.

```bash
./scripts/osdiff.sh doctor --mode market --platform android
./scripts/osdiff.sh list-real-devices
./scripts/osdiff.sh market-run \
  --platform android \
  --app-id com.example.app \
  --baseline-device OLD_SERIAL \
  --candidate-device NEW_SERIAL \
  --open
```

On iOS/macOS:

```bash
./scripts/osdiff.sh doctor --mode market --platform ios
./scripts/osdiff.sh market-run \
  --platform ios \
  --app-id com.example.app \
  --baseline-device OLD_UDID \
  --candidate-device NEW_UDID \
  --ios-app-store-confirmed \
  --open
```

## Fail-closed provenance and environment gate

Before crawling, v0.5 verifies:

- two different physical devices;
- same package/bundle ID;
- exact same app version **and** build number;
- different OS identity (marketing version/API/security patch/build as available);
- market origin policy;
- hardware model policy;
- matching environment settings when both sides expose them (locale, timezone, font/display state, orientation, screen characteristics).

A failed gate is `INVALID` and crawling does not start.

## Deterministic branch isolation

Automatic crawling replays many independent navigation paths. v0.5 treats state isolation as part of coverage validity.

- **Android market mode:** default `android_clear_data`. The target app's data/permissions are cleared between paths with `pm clear`; the Google Play-installed binary remains installed. This makes app-state replay deterministic.
- **iOS real device:** a relaunch cannot reliably clear App Store app state. Therefore automatic coverage is conservatively `PARTIAL` when multiple branches are explored unless `marketMode.iosResetCommand` is configured with a deterministic external reset hook.
- **Virtual Android:** uses target-app data clear between auto-crawl paths.
- **iOS Simulator:** reinstalls the same simulator `.app` between paths.

A non-deterministic reset can never produce `COMPLETE_WITHIN_POLICY` for a branched crawl.

## Automatic discovery coverage

The baseline crawler performs breadth-first exploration and records unique UI states. The candidate device replays the exact baseline paths.

Coverage is forced to `PARTIAL` when any of these occur:

- baseline path replay failure;
- destructive/unsafe action blocked;
- unknown required input;
- action list truncated by `maxActionsPerScreen`;
- depth/screen/path limit reached;
- hierarchy parse failure;
- non-deterministic branch reset.

The report and CLI now use the same authoritative status. `PARTIAL` coverage produces an **INVALID** report banner and exit code `3`.

## Safety

Deny rules always win. A label such as **Continue to Pay** or **Continue to Print** remains blocked even though it also contains an allowed word such as `continue`.

Default safe-mode blocks include destructive/expensive actions such as delete, erase, purchase, pay, send, submit, reset, print/reprint and firmware actions. Use `--unsafe-full-crawl` only with disposable test data and acceptable hardware side effects.

Recognized Android/iOS system UI surfaces can be configured under `crawler.allowedSystemPackages`; unknown external apps stop the branch.

## Security/privacy

On POSIX systems, run folders are created owner-only (`0700`) and artifact files owner-only (`0600`). Test credential values are redacted from captured hierarchy XML. Device IDs are masked/hashed in persisted provenance. Optional screenshot masks can be configured in `artifactPrivacy.sensitiveRegions`.

Use dedicated non-personal test accounts/data. `artifactPrivacy.retentionDays` can be set above `0` to delete old run directories automatically; `0` disables automatic retention cleanup.

## Concurrency

`run`, `auto-run`, and `market-run` are intentionally single-instance. A process lock prevents parallel runs from colliding on Appium/device resources. Run directories also include microseconds and a random token.

## Output

```text
runs/<timestamp>-<token>-market-real/
├── android/ or ios/
│   ├── baseline/
│   └── candidate/
└── report/
    ├── index.html
    ├── comparison.json
    ├── summary.json
    ├── coverage.json
    ├── device-provenance.json
    └── assets/
```

The HTML report includes provenance, environment validation, coverage completeness, reset-isolation status, baseline replay failures, truncated actions, candidate path failures, screenshots, hierarchy changes, behavior failures, and timing regressions.

## Result / exit codes

- `0` — valid complete comparison; no High/Critical regression.
- `1` — setup/tool/configuration failure.
- `2` — valid complete comparison with High/Critical candidate regression.
- `3` — INVALID provenance/execution/hierarchy or PARTIAL automatic coverage.
- `130` — cancelled.

## Other modes

- `auto-run` — automatic emulator/simulator discovery using an APK or Simulator `.app`.
- `run` — deterministic scenario-based emulator/simulator comparison.

## Golden rule

> Change the OS, not the application build.

If version/build differs, the tool refuses to treat the result as an OS differential comparison.


## Hardware-state safety

Automatic safe mode blocks **Pair / Connect / Bluetooth / Print / Reprint / Firmware** actions by default. App-state reset does not reset external printer or Bluetooth hardware state. Use explicit controlled hardware scenarios for these flows; otherwise the automatic coverage result remains partial.
