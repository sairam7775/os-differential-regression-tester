# Future reference and developer handoff — v0.5.0

## Objective and current state

Detect OS-caused regressions in an unchanged Android/iOS production build, including
INSTAX companion apps, without rebuilding or replacing the app. The supplied ZIP
is imported, the baseline reviewed, and unresolved defects documented. No functional
fixes or real-device validations are claimed by the comment/documentation update.

Start with [developer guide](DEVELOPER_GUIDE.md), [architecture](ARCHITECTURE.md),
[configuration](CONFIGURATION.md), [artifacts](ARTIFACTS.md), and
[baseline assessment](BASELINE_ASSESSMENT.md). README is the user-facing entry point;
AGENTS.md and CLAUDE.md at the root orient coding agents.

## Evidence that must accompany the handoff

- Exact source commit and tool/dependency versions, not only release label.
- Actual test count, failures/errors/skips, and installation blockers.
- Distinction between compilation, synthetic probes, mocked tests, live Appium,
  emulator/simulator, and physical-device evidence.
- Current review PR/head and whether Claude returned an actual review.
- Private storage of credentials, device identifiers, screenshots, and hierarchy.

The original suite attempt had 14 passes and three error entries out of 17 loaded
entries; there are 38 test methods in source. Pillow was unavailable and an iOS
mock import failed. Read the assessment for exact commands and limitations.

## Priorities

| Priority | Next work | Completion evidence |
| --- | --- | --- |
| 1 | Safe live-control resolution, Windows locking/cleanup, syntax-preserving privacy, fail-closed artifacts/assertions/traces/reset/identity, CLI/session/setup handling | Focused regressions, complete suite, independent Claude review |
| 2 | Android physical market-run; iOS physical validation when macOS/signing/two iPhones are available | Actual private device evidence tied to commit and unchanged app version/build |
| 3 | Stable state identity, graph destinations/action outcomes, duplicate controls, scoped scrolling/back/tabs/dialogs/dynamic content | Controlled discovery/replay fixtures and honest frontier metrics |
| 4 | Meaningful text/control changes, crash/hang/action evidence, visual noise, timing/severity | Known-good/bad fixtures with false-positive and false-negative checks |
| 5 | Full environment/build details, side-by-side reports, explicit blocker/scope reporting, installation guidance | Reviewer can explain status and limitations from one report |

The [assessment](BASELINE_ASSESSMENT.md) lists concrete defect triggers and the
proposed logical commit sequence. Stabilize the baseline before major features.

## Invariants

Preserve market-installed binaries and exact app version/build matching. Require
positive OS/build/patch difference evidence. A skipped, blocked, or failed branch
must never count as complete. Real iOS relaunch is not a reset. Printer/Bluetooth/
firmware/purchase/destructive operations are excluded from automatic safe mode.
Preserve privacy, report real validation honestly, and document justified
compatibility changes. These requirements outrank optimistic feature metadata.

## Before closing a fix

Reproduce the issue, implement the smallest correct change, add a regression,
run relevant checks, inspect error/cleanup/exit-code behavior, and update the
corresponding known-issue comments and assessment status. Have Claude or another
reviewer verify the exact diff. Do not merge or claim release validation based on
an unanswered review request.
