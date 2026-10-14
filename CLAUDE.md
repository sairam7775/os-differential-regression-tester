# Claude orientation

Follow [AGENTS.md](AGENTS.md) and the user's current instructions.
This repository implements OS Differential Regression Tester v0.5.0, with a
physical-device market mode and separate virtual-device modes.

Start with [developer guide](docs/DEVELOPER_GUIDE.md), then
[baseline assessment](docs/BASELINE_ASSESSMENT.md),
[configuration](docs/CONFIGURATION.md), and [artifacts](docs/ARTIFACTS.md).
The assessment is historical. [Review fixes](docs/REVIEW_FIXES.md) maps the completed
baseline review to implementation/tests and current limitations. Source modules
and helpers have current contract docstrings.

For review, independently verify the current PR head and report actionable findings
with severity, exact file/line references, triggers, impact, and regression tests.
PR #1 is the historical audit against the pre-import branch. Review stabilization
in PR #2, which targets main. Claude re-reviewed a85fb29; the follow-up fixes
still need exact-head approval. CI runs real dependencies
and independent modules. Locally Pillow remains unavailable. No devices were tested.

Never replace market binaries, weaken version/build equality, call skipped coverage
complete, equate iOS relaunch with reset, or perform printer/Bluetooth/firmware/
purchase/destructive operations during automatic safe-mode crawling. Keep test
artifacts private and distinguish mocked checks from real Appium/device evidence.
