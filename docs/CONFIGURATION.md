# Configuration reference — v0.5.0

The valid JSON example is `config/local-config.json`. JSON does not allow comments;
this reference and its existing notes fields explain data without changing defaults.
TOOL_MANIFEST.json is informational feature/evidence metadata, not runtime policy.
Tool-local Appium/driver version pins are in tool-versions.json; Python dependency
ranges remain in requirements.txt. VERSION and osdiff.VERSION remain 0.5.0.

## Loading and override rules

The CLI reads config and resolves relative app paths beside the config file.
Environment variables/user-home syntax in paths is expanded. Explicit --scenario
arguments resolve from cwd; wrappers first change cwd to the repository root.
.env files are not automatically loaded. Set test credential environment variables
in the launching process; do not put actual secrets into JSON or public artifacts.

Global --config precedes the subcommand:

```bash
./scripts/osdiff.sh --config config/project.json market-run --platform android \
  --app-id com.example.app --baseline-device OLD_SERIAL --candidate-device NEW_SERIAL
```

Market app/device IDs come from required CLI flags, not virtual android/ios app
fields. --require-same-model can strengthen model policy; it cannot weaken a true
config value. --allow-android-installer replaces the configured installer list.
The explicit unsafe crawl flag disables keyword filtering but is unsuitable for
the automatic safe-mode business workflow. No flag can waive app version/build equality.

Auto-run --app overrides its virtual binary and clears sample identity to permit
inference; --app-package/--app-activity/--bundle-id are only applied inside that
--app override path in the current code. Without --app, edit JSON app identity.
--baseline-os/--candidate-os override virtual API/runtime values; --device-type
overrides the iOS simulator profile. Run mode uses config plus explicit scenario files.

Values are loosely validated dictionaries. Choose positive limits, non-negative
seconds, 0..1 comparison fractions, valid regexes, and trusted path/identifier strings;
the baseline does not fully enforce those constraints. Unknown input is not proof
of a valid comparison. See BASELINE_ASSESSMENT.md for concrete gaps.

## Shipped fields and defaults

| JSON path | Example default | Meaning / limitation |
| --- | --- | --- |
| `projectName` | `"My Mobile App"` | Display name in report HTML; informational, not an app identifier. |
| `appium.serverUrl` | `"http://127.0.0.1:4723"` | Existing Appium URL or local auto-start target. Baseline readiness checks only HTTP 200; custom base-path/TLS/address support is incomplete. |
| `appium.startupTimeoutSeconds` | `30` | Seconds allowed for owned server startup; independent of device boot, reset, and element timeouts. |
| `appium.logLevel` | `"error"` | Appium server verbosity; higher levels can increase sensitive log exposure. |
| `appium.saveServerLog` | `false` | Retain owned server log after attempted literal redaction when true; default false removes it on normal cleanup. |
| `appium.sensitiveEnvNames` | `["TEST_USER_EMAIL", "TEST_USER_PASSWORD"]` | Environment-variable names whose nonempty values are collected for some log/hierarchy redaction. Other artifact channels are not fully covered. |
| `android.enabled` | `true` | Include Android in virtual run/auto-run and doctor selection; market-run uses its explicit platform argument. |
| `android.appPath` | `"../apps/app-debug.apk"` | Virtual APK path, resolved relative to this config directory. ../apps points to the tool-root apps directory. Not used as a market binary. |
| `android.appPackage` | `"com.example.mobile"` | Virtual target package ID; override/inference behavior differs when auto-run --app is supplied. |
| `android.appActivity` | `".MainActivity"` | Virtual launch activity; use verified app metadata rather than the sample MainActivity. |
| `android.imageTag` | `"google_apis"` | Android SDK system-image flavor used when provisioning virtual devices. |
| `android.abi` | `"x86_64"` | Virtual image ABI; must match the available SDK image and host emulator support. |
| `android.deviceProfile` | `"pixel"` | avdmanager device profile for named virtual devices. |
| `android.autoGrantPermissions` | `false` | Appium permission capability for virtual runtime; market runtime sets false to retain explicit permission flows. |
| `android.noReset` | `false` | Appium session reset intent in virtual modes; independent of crawler resetStrategy between paths. |
| `android.recreateDeviceEachRun` | `true` | Recreate named AVD when true. Emulator launch still uses -wipe-data even when reusing an AVD. |
| `android.baseline.apiLevel` | `"REPLACE_WITH_OLD_STABLE_API"` | Baseline Android API value; replace the sample placeholder with an installed/installable API number. |
| `android.baseline.avdName` | `"OSDIFF_ANDROID_BASELINE"` | Owned baseline AVD name; provisioning can delete/recreate that virtual target. |
| `android.candidate.apiLevel` | `"REPLACE_WITH_NEW_API"` | Candidate API value; runtime verifies the booted emulator's actual API. |
| `android.candidate.avdName` | `"OSDIFF_ANDROID_CANDIDATE"` | Owned candidate AVD name; use a distinct name from baseline. |
| `android.autoResetStrategy` | `"android_clear_data"` | Virtual automatic branch reset; android_clear_data clears target data/permissions while preserving the supplied installation. |
| `ios.enabled` | `true` | Include iOS in virtual selection/doctor. All-platform virtual runs currently skip iOS on non-macOS hosts. |
| `ios.appPath` | `"../apps/MyApp.app"` | Virtual Simulator .app bundle path; not a physical-device IPA. Resolved beside the config file. |
| `ios.bundleId` | `"com.example.mobile"` | Virtual app bundle ID for launch/reset; replace sample identity. |
| `ios.deviceType` | `"iPhone 16"` | Exact Xcode simulator device-type name available on the host. |
| `ios.noReset` | `false` | Appium virtual-session reset capability, independent of branch reset strategy. |
| `ios.recreateDeviceEachRun` | `true` | Delete/recreate matching named simulators when true; wrong-runtime same-name devices can be deleted even when false. |
| `ios.baseline.runtimeVersion` | `"REPLACE_WITH_OLD_STABLE_IOS"` | Replace placeholder with a known installed baseline iOS simulator runtime version. |
| `ios.baseline.simulatorName` | `"OSDIFF_IOS_BASELINE"` | Owned baseline simulator name. |
| `ios.candidate.runtimeVersion` | `"REPLACE_WITH_NEW_IOS"` | Known installed candidate runtime; exact version is preferred over a name substring. |
| `ios.candidate.simulatorName` | `"OSDIFF_IOS_CANDIDATE"` | Owned candidate simulator name, distinct from baseline. |
| `ios.autoResetStrategy` | `"ios_simulator_reinstall"` | Virtual-only ios_simulator_reinstall uninstalls/reinstalls the supplied .app between paths; never use for market binaries. |
| `comparison.checkpointSettleSeconds` | `0.25` | Scenario checkpoint settling after readiness assertions; individual checkpoint settleSeconds overrides it. |
| `comparison.pixelThreshold` | `18` | Per-channel 8-bit pixel difference cutoff after optional blur; changed pixels exceed this threshold. |
| `comparison.visualBlurRadius` | `0.6` | Gaussian blur radius in pixels for measurements; highlighted overlay uses unblurred pixels. |
| `comparison.changedPixelRatioWarning` | `0.01` | Changed-pixel fraction at/above this threshold scores visual REVIEW unless a higher risk applies. |
| `comparison.changedPixelRatioFailure` | `0.05` | Changed-pixel fraction at/above this threshold scores a High visual change. |
| `comparison.meanDifferenceWarning` | `0.015` | Normalized mean channel difference threshold (0..1) for REVIEW. |
| `comparison.durationRegressionFactor` | `1.75` | Candidate duration multiplier relative to a positive baseline; extra-seconds threshold must also pass. |
| `comparison.minimumDurationRegressionSeconds` | `1.0` | Minimum absolute candidate-minus-baseline seconds, used with the duration factor. |
| `comparison.hierarchyChangeWarningRatio` | `0.15` | Multiset hierarchy difference fraction triggering REVIEW; not a semantic missing-control guarantee. |
| `comparison.hierarchyAttributes` | `["type", "class", "name", "label", "resource-id", "content-desc", "enabled", "clickable"]` | Attributes used for hierarchy signatures. Shipped defaults omit Android text and iOS value; this known gap can miss text-only changes. |
| `comparison.hierarchyIgnoreValuePatterns` | `[]` | Case-sensitive Python regex replacements for dynamic hierarchy values before comparison. |
| `comparison.ignoreRegions` | see shipped JSON | Per-platform comparison masks. These do not redact stored screenshots or report originals. |
| `crawler.safeMode` | `true` | Apply deny keyword filtering during discovery. Shared-locator targeting is a confirmed unresolved defect; true is not a safety certification. |
| `crawler.maxScreens` | `120` | Baseline unique-state limit; reaching configured thresholds conservatively makes coverage partial. |
| `crawler.maxDepth` | `12` | Maximum action-path depth from reset launch; action-bearing frontier at this depth makes coverage partial. |
| `crawler.maxActionsPerScreen` | `24` | Cap retained actions after sorting; excess actions are recorded as truncation blockers. |
| `crawler.maxTotalPaths` | `800` | Limit attempted baseline paths, including duplicates and failures. |
| `crawler.enableScrolling` | `true` | Queue one whole-window downward swipe when native scrollable content is recognized; no container/back/upward traversal proof. |
| `crawler.settleSeconds` | `0.6` | Fixed waits around launch/action/capture; included in current wall-clock action measurements. |
| `crawler.afterInputSettleSeconds` | `0.3` | Pause after filling inputs before refreshing source for discovered/candidate checkpoint capture. |
| `crawler.denyKeywords` | array (21 entries); see shipped JSON | Case-insensitive Python regexes checked against selected labels/locator values; deny takes precedence over allow metadata. |
| `crawler.allowKeywords` | `["\\ballow\\b", "\\bwhile using\\b", "\\bok\\b", "\\bcontinue\\b", "\\bnext\\b", "\\bcancel\\b", "\\bnot now\\b"]` | Retained compatibility metadata; currently does not whitelist actions or override denies. |
| `crawler.autoInputRules` | array (2 entries); see shipped JSON | Ordered pattern/env or pattern/value dictionaries; first matching rule supplies input. Prefer environment references and dedicated data. |
| `crawler.fingerprintAttributes` | `["type", "class", "name", "label", "value", "text", "resource-id", "content-desc", "enabled", "clickable", "scrollable"]` | Tree attributes used to discover distinct states; text/value are included by default. |
| `crawler.fingerprintIgnorePatterns` | `["\\b\\d{1,2}:\\d{2}\\b", "\\b\\d{4}-\\d{2}-\\d{2}\\b"]` | Case-sensitive Python regexes replaced with a dynamic marker before fingerprinting; overbroad rules can merge distinct states. |
| `crawler.resetTimeoutSeconds` | `45` | Seconds allowed for each reset subprocess/hook; not a complete crawl/session timeout. |
| `crawler.allowedSystemPackages` | see shipped JSON | Per-platform additions to built-in allowed system surfaces. Empty arrays do not remove built-in allowances. |
| `marketMode.androidAllowedInstallers` | `["com.android.vending"]` | Installer metadata packages accepted for Android origin policy; CLI --allow-android-installer replaces this list when supplied. |
| `marketMode.requireSameHardwareModel` | `false` | Require verified same model when true; false allows model differences with warnings and possible hardware confounding. |
| `marketMode.iosRequireAppStoreAttestation` | `true` | Enable early iOS CLI attestation requirement. Disabling this does not bypass later marketOriginVerified validation. |
| `marketMode.notes` | see shipped JSON | Informational explanation only; not consumed as runtime policy. |
| `marketMode.requireMatchingEnvironment` | `true` | Invalidate differing comparable values when true; missing values are currently skipped. |
| `marketMode.androidResetStrategy` | `"android_clear_data"` | Physical Android reset strategy, normally android_clear_data; use only strategies preserving the market binary. |
| `marketMode.iosResetStrategy` | `"relaunch"` | Physical iOS default relaunch is non-deterministic; branched baseline exploration is partial. |
| `marketMode.iosResetCommand` | `null` | Null or operator-owned JSON argument array. Overrides strategy; udid/appId format placeholders are expanded and exit zero is trusted. Must preserve binary. |
| `artifactPrivacy.privatePermissions` | `true` | Informational setting in this baseline; helpers attempt POSIX permissions unconditionally and do not consult this value. Windows ACLs are unchanged. |
| `artifactPrivacy.notes` | see shipped JSON | Informational privacy limitations; not executable validation. |
| `artifactPrivacy.sensitiveRegions` | `{"android": [], "ios": []}` | Per-platform screenshot rectangles blacked out before storage. Empty lists mean no pixel redaction. |
| `artifactPrivacy.retentionDays` | `0` | Zero disables cleanup; positive days deletes old tool-root run directories based on directory mtime. |

## Nested region and input-rule fields

Both comparison.ignoreRegions and artifactPrivacy.sensitiveRegions are platform
maps to arrays of rectangle dictionaries. The former only affects measurement;
the latter overwrites stored screenshot pixels before artifacts/report copies.

| Region field | Meaning |
| --- | --- |
| `x` | Left coordinate: normalized fraction or pixels according to normalized. |
| `y` | Top coordinate: normalized fraction or pixels. |
| `width` | Region width in normalized fractions or pixels. |
| `height` | Region height in normalized fractions or pixels. |
| `normalized` | True uses image dimensions for fractions; false/absent uses pixel coordinates. |

Default comparison rectangles mask the upper 3.5% of Android and 5.5% of iOS
screens. These are comparison noise policies, not privacy guarantees. Sensitive
regions default empty; configure them using known test UI geometry.

Each autoInputRules item uses `pattern` (case-insensitive regex) and `env` (variable
name) or `value` (inline fallback). Pattern matching uses the selected field label.
The first match wins. A missing/empty value creates a blocker. Duplicate controls,
failed clears, encoded secrets, and inline-value redaction need stabilization.

## Reset policy

| Strategy | Current behavior | Intended allowed use |
| --- | --- | --- |
| android_clear_data | Serial-specific pm clear, then activate | Android target data/permission isolation; binary unchanged |
| ios_simulator_reinstall | simctl uninstall/install supplied .app | Virtual iOS only; never physical market binaries |
| reset_command | Argument-array subprocess; zero exit treated deterministic | Explicit safe operator hook preserving market binary |
| relaunch | Terminate/activate only; non-deterministic | Real iOS fallback with honest partial coverage |
| driver | No deterministic reused-session reset proof | Compatibility path; do not claim branched complete coverage |

Normal market runtime prevents binary supply; helpers still need explicit mode
authorization. Android clear does not reset external hardware/server state.
Real-iOS command placeholders `{udid}` and `{appId}` are expanded with str.format;
there is no shell evaluation or bundled reset tool. See REAL_DEVICE_MARKET_MODE.md.

## Evidence and privacy

Feature flags and notes do not establish tested behavior. Primary provenance IDs
are masked/hashed; errors/trace/assertion metadata is not yet fully sanitized.
Literal hierarchy redaction can corrupt XML. POSIX permissions are best-effort,
privatePermissions is not a runtime toggle, and Windows ACLs are unchanged.
Retained screenshots may contain unmasked personal information. Use dedicated
non-personal data and preserve the handoff safety/validity constraints.

See ARTIFACTS.md for output fields, SCENARIOS.md for scenario data, and
BASELINE_ASSESSMENT.md for actual validation results and unfinished fixes.
