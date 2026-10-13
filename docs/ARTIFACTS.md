# Artifact data contracts — v0.5.0

These fields describe the current dictionaries written by the code, not a formal
JSON schema. Keep extensions backward compatible or document migrations. Values
in examples are synthetic; do not publish real credentials, device identifiers,
screenshots, or hierarchy. Retention is local and disabled by default.

## Paths and mode distinctions

`runs/<local timestamp>-<random token>[-auto|-market-real]/<platform>/<role>/`
contains each target's evidence. `role` is baseline/candidate. A checkpoint is
`<scenario>/<checkpoint>/screen.png`, `source.xml`, and `state.json`.
Automatic modes use scenario `auto_crawl` and baseline-generated checkpoint names.
The candidate preserves those names so comparison can join corresponding paths.

`report/` contains HTML, comparison/summary JSON, and screenshot/diff copies.
Automatic modes add coverage.json; market mode adds device-provenance.json.
Run timestamps/epochs use local time/time.time respectively, not a guaranteed UTC
identifier. Durations currently use wall clock and configured settling sleeps.

## Runtime dictionaries (in memory)

| Field/group | Meaning |
| --- | --- |
| `udid`, `deviceName` | Actual selected target ID and readable name; raw IDs are needed in memory |
| `appPath` | Resolved supplied binary for virtual modes; None for market runtime |
| `appPackage/appActivity`, `bundleId` | Android launch identity or iOS bundle |
| `preinstalled`, `noReset`, `autoGrantPermissions` | Appium install/reset/permission intent |
| `resetStrategy`, optional `resetCommand/adbPath` | Branch reset operation and required tool/argument details |
| `checkpointSettleSeconds`, `sensitiveEnvNames/sensitiveRegions` | Capture settling and privacy inputs |

Normal market runtimes omit the `app` capability; do not persist full runtime
dictionaries as public evidence. See configuration/reset documentation.

## Checkpoint state.json

Scenario fields: `scenario`, `checkpoint`, `platform`, `assertions`, `recentActions`,
`windowSize`, `capturedEpoch`. Assertions contain `type`, `passed`, `message`.
Scenario recent actions contain type/status/error/duration since the prior checkpoint.

Automatic states additionally contain `crawler=true`, `stateFingerprint`, `path`,
and `metadata`. Metadata records depth/action count/input results/foreground on
baseline; candidate adds `replayedFromBaseline` and `baselineStateFingerprint`.
Automatic `recentActions` is the complete replay trace for the retained path.
Different trace meanings between modes are intentional and must be preserved.

The screenshot is optionally blacked out before storage. source.xml is captured
native hierarchy after literal credential replacement; current replacement can
make XML invalid. Path/trace/assertion/error metadata is not fully sanitized.
Fingerprint and capture can represent different pre/post-input states in baseline.

## run-summary.json

This is a list of scenario records, not one summary dictionary. Scenario execution
records `scenario`, `status`, `error`, `actions`, `checkpointsCaptured`,
`completedSteps`, and optional `traceback`. Checkpoint assertions are in state.json,
not copied into the action list. Continue-on-failure can leave status passed.

Automatic summaries contain one `auto_crawl` entry with platform/status/error,
an empty actions list, and a `crawler` count/coverage object. Baseline status means
at least one screen was discovered. Candidate status currently means the baseline
had screens, even if replay paths failed; consult replay evidence/checkpoints.
Malformed/missing/incomplete summary handling needs further fail-closed checks.

## Discovery graph and candidate replay

`auto-crawl-graph.json` contains:

| Fields | Meaning |
| --- | --- |
| `platform`, `mode` | Platform and `auto_crawl` identifier |
| `screens` | First-seen checkpoint/fingerprint/depth/path/action count/labels |
| `edges` | Queued `from` checkpoint, action, child depth; no reliable destination yet |
| `blockedActions`, `blockedInputs` | Discovered checkpoint blocker records with label/reason |
| `replayFailures` | Baseline failed paths with error and replay trace |
| `limits` | Max screens/depth/attempted paths |
| `limitReached`, `depthFrontierReached`, `queueRemaining` | Remaining/frontier indicators |
| `actionsTruncated`, `attemptedPaths`, `discoveredScreens`, `baselineReplayFailures` | Counts; paths include duplicates and failures |
| `deterministicReset`, `resetIsolationStatus` | Aggregate baseline reset evidence |
| `coverageStatus`, `coverageNote` | COMPLETE_WITHIN_POLICY/PARTIAL plus scope statement |

Actions contain `kind` (tap/scroll_down), `label`, and for taps `locators`,
`ordinal`, `bounds`. Bounds store x/y/width/height. Locator candidates contain
strategy/value. These records are replay hints, not verified safe-control identities.
Input results store label/source or label/reason, not intended input values, but
labels and errors can still reveal sensitive content.

Trace entries contain `index`, `action`, `status`, `durationSeconds`, `inputsFilled`,
`blockedInputs`, and an error when failed. The trace can be incomplete on failure.

`auto-crawl-replay.json` contains platform/mode, `baselineScreens`,
`reproducedScreens`, `failedPaths`, and `deterministicReset`. Failed paths store
checkpoint/error/path/trace. Reproduced counts captures rather than matched screens.

## Coverage and provenance

coverage.json maps platform to automatic counts: discoveredBaselineScreens,
candidateScreensReproduced, candidatePathFailures, baselineReplayFailures,
blockedUnsafeActions, blockedInputs, actionsTruncated, depthFrontierReached,
limitReached, coverageStatus, resetIsolationStatus, coverageNote. It currently
derives reset/coverage status from baseline only. Intermediate replay blockers
and candidate reset/input evidence remain incomplete. Blocked-action count also
includes non-keyword blockers such as truncation/parse failures.

device-provenance.json contains mode=`real-device-market-build`,
toolInstalledApp=false, baseline/candidate device facts, and validation.
Facts include platform, physicalDevice, manufacturer/model/modelVerified/name,
OS release/API/patch/fingerprint, environment/screen size, app ID/version/build,
launch activity (Android), installer/allowed installers, origin verification/method,
and toolInstalledApp. The primary deviceId is replaced by deviceIdMasked and
deviceIdSha256; marketOriginRaw is removed. Other metadata is not a complete
privacy boundary.

Validation contains valid/errors/warnings, sameHardwareModel,
sameAppVersionAndBuild, environmentDifferences, baselineOsIdentity,
candidateOsIdentity. OS tuples are persisted as JSON arrays; unknown components
are empty strings. Missingness must not be interpreted as a verified OS difference.

## Comparison, scoring, and final summary

comparison.json is a list of checkpoint and synthetic execution/provenance rows.
Common fields: platform/scenario/checkpoint, comparisonStatus, riskScore/severity,
reasons, behaviorRegressions, hierarchyChangeRatio, visual, and normally
missingBaseline/missingCandidate. Some synthetic provenance rows omit missing flags.
Compared pairs add hierarchyValid and relative baseline/candidate/diff image paths.

visual contains changedPixelRatio, meanDifference, dimensionChanged,
baselineSize, candidateSize. Hierarchy differences use multiset signatures;
default text/value omissions are documented in the assessment. Behavior includes
assertion_regression, action_failure, duration_regression, and evidence errors.

Score is the maximum matching risk, not a sum. Critical >=90, High >=70,
Medium >=40, Low <40; scores >=70 yield FAIL, >=40 yield REVIEW. Hierarchy parse
invalidity yields INVALID regardless of score. Numeric thresholds are policy,
not validated statistical confidence.

summary.json contains overallStatus, checkpoints, highRisk, review, invalid,
checkpointInvalid, coverageInvalid, provenanceInvalid, report. `invalid` sums
invalid rows and aggregate flags; it is not a count of unique root causes.
`checkpoints` currently counts all non-synthetic rows, including INVALID ones.
highRisk excludes INVALID rows. Overall precedence is INVALID > FAIL > REVIEW > PASS.
An empty result list without supplied invalid metadata can currently yield PASS;
do not invoke reporting as a substitute for evidence validation.

CLI exits use invalid/highRisk counts (0/2/3), exceptions use 1, cancellation 130.
Auto-run additionally checks partial coverage. A report or exit zero alone does
not repair the known evidence gaps or prove actual physical-device validation.
