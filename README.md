# OS Differential Regression Tester — v0.5.0

Compare one mobile application version/build on baseline and candidate OS
identities, using Appium to collect screenshots, native hierarchy, action traces,
and timing evidence. The preferred production workflow uses the same
market-installed app on two physical devices; developers do not rebuild that app.

## Current development status

This is the imported hardened baseline, with unresolved safety and validity
defects. [The baseline assessment](docs/BASELINE_ASSESSMENT.md) records actual
results, confirmed reproductions, and the prioritized stabilization plan. No
physical-device, emulator/simulator, or live Appium validation has been performed.
The local Claude review request is tracked in [PR #1](https://github.com/sairam7775/os-differential-regression-tester/pull/1);
a running CLI command is not evidence of a completed review.

The baseline test attempt produced 14 passing methods, one test-method error,
and two discovery errors; 38 test methods exist in source. Pillow was unavailable,
and the iOS metadata test's partial Appium mock caused an import error.
Do not describe the full suite as passing. Documentation and comments explain
current behavior; they do not repair the known issues.

## Choose a mode

| Command | Devices | App source | Execution |
| --- | --- | --- | --- |
| `market-run` | Two physical Android phones or iPhones | Already installed from the store; version/build equality is gated | Baseline discovery, candidate path replay |
| `auto-run` | Android emulators or iOS simulators | Operator-supplied APK or Simulator `.app` | Baseline discovery, candidate path replay |
| `run` | Android emulators or iOS simulators | Configured APK or Simulator `.app` | Explicit scenario steps/checkpoints |

Virtual modes use the same configured binary path on both targets; they do not
independently inspect installed version/build metadata as market mode does.
iOS execution requires macOS and Xcode. `doctor`, `list-targets`,
`list-real-devices`, and `open-report` are supporting commands.

## Install and run locally

Prerequisites: Python 3.10+, Node `^20.19.0 || ^22.12.0 || >=24`, npm 10+,
Java/`JAVA_HOME` and Android platform-tools for Android, or macOS/Xcode/signing
for iOS. Appium/driver pins are in `config/tool-versions.json`; Python dependency
ranges are in `requirements.txt`.

On Windows, from the repository root:

```powershell
.\scripts\setup-local.ps1
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\scripts\osdiff.ps1 doctor --mode market --platform android
.\scripts\osdiff.ps1 list-real-devices
```

On macOS/Linux:

```bash
./scripts/setup-local.sh
./.venv/bin/python -m unittest discover -s tests -v
./scripts/osdiff.sh doctor --mode market --platform android
./scripts/osdiff.sh list-real-devices
```

Check dependency installation errors explicitly, particularly on Windows where
the baseline setup script does not check every Python command's exit code.
The CLI currently imports Pillow even for help/doctor; install Python dependencies
before using those commands. See [quick start](docs/QUICKSTART.md) for preparation.

## Physical-device market comparison

Install the exact same market version/build on both dedicated devices, disable
automatic app updates, align comparable environment settings, and use test accounts.
After reviewing the [known safety defects](docs/BASELINE_ASSESSMENT.md), a configured
Android command has this form:

```bash
./scripts/osdiff.sh market-run \
  --platform android --app-id com.example.app \
  --baseline-device OLD_SERIAL --candidate-device NEW_SERIAL --open
```

For iOS on macOS:

```bash
./scripts/osdiff.sh market-run \
  --platform ios --app-id com.example.app \
  --baseline-device OLD_UDID --candidate-device NEW_UDID \
  --ios-app-store-confirmed --open
```

These are command templates, not evidence that the baseline is safe or validated.
All identifiers are placeholders. Market runtimes omit the Appium `app`
capability. Android normally clears only app data/permissions between paths;
it preserves the installed binary. iOS store origin requires operator attestation.
See [market-mode details](docs/REAL_DEVICE_MARKET_MODE.md).

## Reset, safety, and coverage

Android `android_clear_data` uses `pm clear`; real iOS `relaunch` does not reset
app data. A configured external iOS reset command is trusted when it exits zero,
and must preserve the store binary. Simulator reinstall is a virtual-mode operation.

Baseline discovery records blockers, failures, truncation, and exhausted limits.
`PARTIAL` automatic coverage makes the report `INVALID`. A branched baseline
with relaunch-only reset is partial. Current candidate reset/input gaps are
documented; `COMPLETE_WITHIN_POLICY` is not proof of complete app coverage.

Safe mode intends to block pairing, Bluetooth connections, printing/reprinting,
firmware, purchases, and destructive actions. Deny patterns override allowed
words, but a confirmed shared-locator defect can still target a blocked control.
Keep safe mode enabled and fix live target resolution before hardware validation.
Explicit scenarios do not apply crawler deny rules automatically. Never use
automatic safe mode for printer or other hardware side effects.

## Results and artifacts

| Exit code | Meaning |
| --- | --- |
| `0` | Reported PASS/REVIEW with no reported High/Critical regression |
| `1` | Setup/configuration/tool exception |
| `2` | Reported candidate High/Critical regression |
| `3` | INVALID comparison or incomplete automatic coverage |
| `130` | Cancelled |

The intended compatibility sign-off also requires valid baseline evidence, exact
app version/build, verified OS difference, complete explored scope, valid artifacts,
and deterministic reset on both devices. Known baseline gaps mean exit zero alone
is not sufficient evidence. Overall report precedence is INVALID, FAIL, REVIEW, PASS.

```text
runs/<local-timestamp>-<token>[-mode]/
  android/ or ios/
    baseline/    # summaries, graph, scenario/checkpoint artifacts
    candidate/   # summaries, replay result, corresponding artifacts
  report/
    index.html   # side-by-side images and scored differences
    comparison.json
    summary.json
    assets/
    coverage.json          # automatic modes
    device-provenance.json # market mode
```

Artifacts are local. POSIX permissions are applied best-effort; Windows ACLs are
not configured. Screenshot masking is opt-in. Provenance masks/hashes primary
device IDs, but errors and traces need further sanitization; current XML redaction
can corrupt syntax. Use dedicated non-personal data and preserve artifact privacy.
Retention is disabled by default; positive `retentionDays` deletes old run folders.
The single-run lock also has known Windows and cleanup defects.

## Developer reading order

1. [Developer guide](docs/DEVELOPER_GUIDE.md): entry points, contracts, testing, and handoff.
2. [Architecture](docs/ARCHITECTURE.md): data flow and resource ownership.
3. [Configuration](docs/CONFIGURATION.md): every default field and CLI precedence.
4. [Artifacts](docs/ARTIFACTS.md): JSON/XML/image field meanings and result semantics.
5. [Baseline assessment](docs/BASELINE_ASSESSMENT.md): issues requiring fixes.
6. [Future reference](docs/FUTURE_REFERENCE.md): priorities and next-review checklist.

Agent instructions are in [AGENTS.md](AGENTS.md); Claude-specific orientation is in
[CLAUDE.md](CLAUDE.md). Follow [automatic discovery](docs/AUTO_DISCOVERY.md) and
[scenario format](docs/SCENARIOS.md) when extending existing behavior.
