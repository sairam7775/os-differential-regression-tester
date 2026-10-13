# Physical devices and market-installed builds

## Contract

`market-run` compares two physical targets with the same application ID, exact
marketing version, and exact build. Its normal runtime contains no app binary:
`preinstalled=True`, `noReset=True`, `appPath=None`. Shared Appium options omit
the `app` capability. The operator installs from Google Play/App Store beforehand.
Never add sideloading, upgrade/downgrade, reinstall, or OS modification to this path.

## Preflight data

Android probes authorization, emulator indicators, installation, package
versionCode/versionName, installer-source metadata, launch activity, manufacturer,
model, OS release/API/patch/fingerprint, and comparable environment facts.
Each probe targets the supplied serial. Current ADB lookup requires PATH even
though other helpers support SDK-root lookup.

iOS uses a temporary XCUITest session for device metadata and `mobile: listApps`
with `returnAttributes`. Version/build are machine-read; App Store origin is
operator attestation with `--ios-app-store-confirmed`. The probe quits its session.
Missing simulator metadata currently results in assumed physical-device status;
do not describe that as positive hardware proof.

`validate_market_pair` rejects equal device IDs, platform/app mismatch, unavailable
or unequal app version/build, equal OS tuples, unverified origin, and policy
violations. Same model is optional; comparable environment values are required
to match by default. Unknown environment fields are skipped. Missing OS fields
can currently create a false tuple difference; positive OS evidence and post-run
app identity revalidation remain known work. See [assessment](BASELINE_ASSESSMENT.md).

## Reset strategy

| Environment | Default | What changes |
| --- | --- | --- |
| Physical Android | `android_clear_data` | Target data/permissions via serial-specific `pm clear`; binary preserved |
| Physical iOS | `relaunch` | Process only; data is not cleared and reset is non-deterministic |
| iOS with external hook | `reset_command` | Operator-defined data reset; trusted on exit zero |

Relaunch-only branched baseline exploration is partial. App-data reset does not
reset printer/Bluetooth/server/account state. Current coverage summary uses only
baseline isolation; candidate reset evidence must be incorporated during stabilization.

A hook is configured as an argument array, not shell text:

```json
{"iosResetCommand": ["/absolute/path/reset-test-state", "--udid", "{udid}", "--bundle", "{appId}"]}
```

The executable must exist and must preserve the store binary. `{udid}` and
`{appId}` are expanded with Python format substitution. Timeout comes from
`crawler.resetTimeoutSeconds`. No generic reset utility is supplied by this project.

## Safety and privacy

Keep safe mode enabled for INSTAX and other companion apps. Pairing, connections,
Bluetooth, printing/reprinting, firmware, payments, and destructive actions are
intended deny targets. A confirmed filtered-ordinal/live-locator defect means
keyword filtering alone is insufficient; fix resolution before hardware validation.
Use separately reviewed controlled scenarios for hardware operations, never an
automatic safe-mode crawl. Explicit scenario mode has no crawler deny filter.

Only the primary device ID in persisted provenance is masked/hashed. Raw installer
output is dropped there; traces and errors still need sanitization. POSIX private
permissions are best-effort, Windows ACLs are unchanged, and screenshot masks are
opt-in. Keep artifacts private and use non-personal accounts/data.

## Actual acceptance evidence

Record exact tested commit, dependency/driver versions, private target IDs,
store app/version/build, verified OS/build/patch, model/environment, launch,
reset, discovery, replay, capture, and report/exit-code outcomes. Verify the app
binary/build stays unchanged through the run. No such physical-device validation
has been performed for this baseline. [Quick start](QUICKSTART.md) contains commands.
