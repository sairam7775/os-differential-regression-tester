# Quick Start — v0.5 Physical Market Devices

## 1. Install and validate prerequisites

Android physical-device mode:

```bash
./scripts/setup-local.sh
./scripts/osdiff.sh doctor --mode market --platform android
```

Windows:

```powershell
.\scripts\setup-local.ps1
.\scripts\osdiff.ps1 doctor --mode market --platform android
```

iOS/macOS:

```bash
./scripts/setup-local.sh
./scripts/osdiff.sh doctor --mode market --platform ios
```

`doctor --mode market` does not require Android emulator/sdmanager/avdmanager when only physical Android devices are being used.

## 2. Prepare two physical phones

- Baseline phone: old/stable OS.
- Candidate phone: new/released OS or new patch/build.
- Prefer the same hardware model.
- Install the **exact same market app version/build** on both.
- Keep locale/timezone/display settings aligned.
- Disable automatic app updates during the comparison window.
- Use dedicated automation accounts/data.

## 3. Identify devices

```bash
./scripts/osdiff.sh list-real-devices
```

## 4. Android market run

```bash
./scripts/osdiff.sh market-run \
  --platform android \
  --app-id com.example.app \
  --baseline-device OLD_SERIAL \
  --candidate-device NEW_SERIAL \
  --open
```

Android app data is cleared between crawler branches to make replay deterministic. This does **not** uninstall or replace the Play Store binary.

## 5. iOS market run

```bash
./scripts/osdiff.sh market-run \
  --platform ios \
  --app-id com.example.app \
  --baseline-device OLD_UDID \
  --candidate-device NEW_UDID \
  --ios-app-store-confirmed \
  --open
```

A real iPhone cannot be generically reset to a clean App Store app-data state through public XCUITest automation. With the default `iosResetStrategy: relaunch`, branched automatic discovery is therefore `PARTIAL`/`INVALID` for full sign-off. If your app/test environment has a deterministic reset utility, configure `marketMode.iosResetCommand` as a JSON argument array; no shell is used.

Example shape:

```json
"iosResetCommand": [
  "/absolute/path/reset-test-state.sh",
  "--udid", "{udid}",
  "--bundle", "{appId}"
]
```

## 6. Read the result

A clean automated sign-off requires:

```text
Provenance/environment gate: PASS
Coverage: COMPLETE_WITHIN_POLICY
Reset isolation: DETERMINISTIC
High/Critical regressions: 0
Overall status: PASS or REVIEW
```

`PARTIAL` coverage, malformed hierarchy capture, provenance mismatch, or failed baseline execution makes the report `INVALID`.


## Hardware-state safety

Automatic safe mode blocks **Pair / Connect / Bluetooth / Print / Reprint / Firmware** actions by default. App-state reset does not reset external printer or Bluetooth hardware state. Use explicit controlled hardware scenarios for these flows; otherwise the automatic coverage result remains partial.
