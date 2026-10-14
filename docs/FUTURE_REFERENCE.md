# Future reference and developer handoff - v0.5.0

## Objective and current state

Detect OS regressions in an unchanged Android/iOS production build, including
INSTAX companion apps, without rebuilding or replacing the app. Claude completed
the baseline review in PR #1. PR #2 implements stabilization fixes and targets main.
The follow-up diff still needs independent review and physical-device acceptance.

Start with [REVIEW_FIXES.md](REVIEW_FIXES.md), [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [CONFIGURATION.md](CONFIGURATION.md), and
[ARTIFACTS.md](ARTIFACTS.md). [BASELINE_ASSESSMENT.md](BASELINE_ASSESSMENT.md)
preserves the original results and findings; it is historical.

## Handoff evidence

Record exact commit and dependencies, actual test counts/errors/skips, independent
review status, and separate evidence for synthetic tests, real SDK serialization,
live Appium, virtual targets, and physical devices. Keep credentials, identifiers,
screenshots, and hierarchy private. CI installs real dependencies and runs the full
suite and independent modules on Windows/Linux Python 3.11/3.14. Local Pillow
installation remains unavailable; no device execution is claimed.

## Priorities

| Priority | Remaining work | Required evidence |
| --- | --- | --- |
| 1 | Review stabilization diff; broaden live session/setup acceptance where available | Exact-head independent review and genuine test results |
| 2 | Android market-run on two phones; iOS when macOS/signing/two iPhones exist | Private evidence for unchanged app/build, positive OS difference, launch/reset/replay/capture/report |
| 3 | Graph destinations/outcomes, duplicate edges, scoped scrolling/back/tabs/dialogs/dynamic content | Controlled fixtures and honest blocked/frontier metrics |
| 4 | Semantic missing controls, crash/hang evidence, visual noise, repeated timing samples/severity | Known-good/bad fixtures with false-positive/negative analysis |
| 5 | Full environment/build/blocker/scope details in reports and installation guidance | A reviewer can explain status and limitations from the report |

## Invariants and closing changes

Preserve market binaries and exact app version/build equality. Require positive
known OS difference. Skipped, blocked, failed, or missing branches are incomplete.
iOS relaunch does not reset data. Pairing/connections/printing/firmware/payment/
destructive actions remain excluded from automatic safe mode. Preserve privacy
and document justified compatibility changes.

For each fix, reproduce, implement a focused change, add a regression, run appropriate
checks, inspect cleanup/exit codes, and update comments/data/docs. Review the exact
current diff; a PR or passing synthetic tests alone do not establish physical safety.
Do not mark original audit threads approved merely because fixes were pushed elsewhere.
