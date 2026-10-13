# Local quick start — v0.5.0

Read the [baseline assessment](BASELINE_ASSESSMENT.md) first: shared locator
resolution, Windows locking, redaction, and validity defects remain unresolved.
The following describes setup and command shapes; it is not device test evidence.

## 1. Install prerequisites

Use Python 3.10+, supported Node/npm as listed in README, and network/package
access for installation. Android needs Java/`JAVA_HOME` and Android SDK platform
tools with `adb` on PATH. Virtual Android also needs SDK command-line tools and
an emulator. iOS needs macOS/Xcode, installed simulator runtimes for virtual
testing, or trusted real iPhones with Developer Mode and WDA signing for market mode.

Windows:

```powershell
.\scripts\setup-local.ps1
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\scripts\osdiff.ps1 doctor --mode market --platform android
```

macOS/Linux:

```bash
./scripts/setup-local.sh
./.venv/bin/python -m unittest discover -s tests -v
./scripts/osdiff.sh doctor --mode market --platform android
```

On macOS, substitute `--platform ios` to inspect iOS prerequisites. Keep the full
installation output: Windows setup does not yet check every Python exit code.
If `python` is only a Windows Store alias, install/select a working interpreter
before setup. The wrappers use this project's `.venv`, not an arbitrary activated one.

## 2. Configure dedicated test data

`config/local-config.json` is an example. Set application IDs, environment-backed
test credentials, masks, and policy values using [configuration guidance](CONFIGURATION.md).
Do not commit secrets or personal accounts. The tool does not automatically load
`.env`; set `TEST_USER_EMAIL`/`TEST_USER_PASSWORD` in the process environment.

Paths in JSON resolve relative to that JSON file's directory. Global `--config`
precedes the subcommand:

```bash
./scripts/osdiff.sh --config config/project.json doctor --mode market --platform android
```

## 3. Prepare and inspect physical devices

Install the same public/store version and build on both dedicated phones. Prefer
the same model and match locale, timezone, font/display/orientation settings.
Disable automatic app updates for the comparison window. Authorize ADB or trust
the iPhones in Xcode. These steps do not modify the application binary.

```bash
./scripts/osdiff.sh list-real-devices
```

The listing does not launch or validate the app. Device IDs printed here are for
targeting and should not be pasted into public reports.

## 4. Market command templates

```bash
./scripts/osdiff.sh market-run --platform android \
  --app-id com.example.app --baseline-device OLD_SERIAL \
  --candidate-device NEW_SERIAL --open
```

On Windows, use `.\scripts\osdiff.ps1` with the same arguments on one line.
Android discovery clears target app data/permissions between paths. It does not
uninstall the store binary, but it does require disposable test state.

On macOS:

```bash
./scripts/osdiff.sh market-run --platform ios \
  --app-id com.example.app --baseline-device OLD_UDID \
  --candidate-device NEW_UDID --ios-app-store-confirmed --open
```

Default real-iOS relaunch-only branched crawling is partial. A custom reset hook
must deterministically restore data without replacing the market binary; exit
zero is trusted by the current implementation. See [market mode](REAL_DEVICE_MARKET_MODE.md).

## 5. Virtual modes

Provide a trusted APK or Simulator `.app`, actual OS versions, and app-specific
scenario identifiers. Sample config contains `REPLACE_WITH_*` OS values and sample
scenario locators; these must be replaced.

```bash
./scripts/osdiff.sh auto-run --platform android --app apps/test.apk \
  --baseline-os OLD_API --candidate-os NEW_API
./scripts/osdiff.sh run --platform android --scenario scenarios/core_navigation.json
```

`OLD_API`/`NEW_API` are placeholders. Virtual setup may recreate/wipe named devices
and install the supplied binary. Do not use it for physical market testing.

## 6. Read the result

Inspect report status, provenance, coverage blockers, reset evidence, and actual
failures together. Partial coverage is INVALID, not a compatibility PASS.
Exit zero means no reported High/Critical regression; unresolved baseline gaps
still prevent relying on that alone. [Artifact documentation](ARTIFACTS.md)
explains output fields and [tests README](../tests/README.md) explains test scope.
