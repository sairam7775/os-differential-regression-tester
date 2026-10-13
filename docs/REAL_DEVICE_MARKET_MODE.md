# Real Device + Market Build Mode — v0.5

## Purpose

`market-run` compares the exact same public/store app build on two physical devices so OS/build impact can be isolated from application-code changes.

## The tool never replaces the market binary

It does not download from a store, supply an APK/IPA to Appium, upgrade/downgrade the app, or alter the phone OS.

### Android app-data reset

For automatic branch isolation, Android market mode defaults to:

```text
resetStrategy = android_clear_data
```

This runs `pm clear <package>` between paths. It clears app data/permissions but **does not uninstall or replace the Google Play-installed package**. Test credentials are then re-entered using configured input rules.

### iOS app-data reset

Public real-device XCUITest automation cannot generically clear an App Store app's data while preserving the installed store binary. A relaunch alone is not deterministic for stateful branches, so branched iOS automatic discovery is marked `PARTIAL` by default.

If the team has a safe test-state reset utility, configure:

```json
"iosResetCommand": ["/absolute/reset-tool", "--udid", "{udid}", "--bundle", "{appId}"]
```

The command is executed directly as an argument array (`shell=False`).

## Provenance/environment gate

The run proceeds only when:

```text
physical devices                       PASS
same application ID                    PASS
same app marketing version             PASS
same app build number                  PASS
different OS identity/build/patch      PASS
market-origin policy                   PASS
required hardware model identity       PASS
matching comparable environment        PASS
```

Android records release/API/security patch/build fingerprint. iOS records platform version and OS build where available.

## iOS market provenance

Bundle/version/build are machine-verified. App Store origin remains an explicit operator attestation because public XCUITest app metadata does not provide a trustworthy App Store-origin field.

## Device identifiers

Full ADB serials/iOS UDIDs are used only in-memory to target devices. Persisted provenance masks the identifier and stores a SHA-256 hash rather than the full value.

## INSTAX / hardware-companion apps

Keep automatic safe mode enabled. Print/reprint/firmware/reset/payment-style actions are blocked and make automatic coverage PARTIAL. Validate real printer actions using explicit controlled scenarios with limits such as one print per case and no automatic firmware update/factory reset.


## Hardware-state safety

Automatic safe mode blocks **Pair / Connect / Bluetooth / Print / Reprint / Firmware** actions by default. App-state reset does not reset external printer or Bluetooth hardware state. Use explicit controlled hardware scenarios for these flows; otherwise the automatic coverage result remains partial.
