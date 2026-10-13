# Claude orientation

Follow [AGENTS.md](AGENTS.md) and the user's current instructions.
This repository implements OS Differential Regression Tester v0.5.0, with a
physical-device market mode and separate virtual-device modes.

Start with [developer guide](docs/DEVELOPER_GUIDE.md), then
[baseline assessment](docs/BASELINE_ASSESSMENT.md),
[configuration](docs/CONFIGURATION.md), and [artifacts](docs/ARTIFACTS.md).
The assessment documents unresolved bugs; comments describe behavior without
claiming fixes. Source modules and helper functions have contract docstrings.

For review, independently verify the current PR head and report actionable findings
with severity, exact file/line references, triggers, impact, and regression tests.
The retrospective review PR's base is the pre-import branch rather than main.
The original full test suite did not pass; no physical-device testing is claimed.

Never replace market binaries, weaken version/build equality, call skipped coverage
complete, equate iOS relaunch with reset, or perform printer/Bluetooth/firmware/
purchase/destructive operations during automatic safe-mode crawling. Keep test
artifacts private and distinguish mocked checks from real Appium/device evidence.
