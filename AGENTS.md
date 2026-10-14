# Developer and coding-agent instructions

## Read first

Read README.md, docs/DEVELOPER_GUIDE.md, docs/ARCHITECTURE.md,
docs/CONFIGURATION.md, docs/ARTIFACTS.md, docs/BASELINE_ASSESSMENT.md, and
docs/FUTURE_REFERENCE.md. Inspect relevant modules/tests before editing them.
This is v0.5.0 with review stabilization fixes; real-device validation is pending.
Read docs/REVIEW_FIXES.md for current status; the baseline assessment is historical.

## Preserve the business invariants

- Preserve market-installed app binaries. Market runtimes must not supply an
  APK/IPA/Simulator `.app` or request installation/replacement of the target app.
- Require identical application marketing versions and builds, and positive
  verified OS/build/patch difference evidence for an OS differential claim.
- Skipped, blocked, failed, or otherwise unexplored branches are incomplete.
  Incomplete automatic coverage must never produce a compatibility PASS.
- Real iOS relaunch does not reset its data. Preserve honest reset reporting
  and keep virtual simulator reinstall operations out of physical market mode.
- No Bluetooth pairing/connections, printing/reprinting, firmware, purchases,
  or destructive operations during automatic safe-mode crawling.
- Preserve artifact privacy. Never commit actual credentials, raw device IDs,
  personal screenshots/hierarchy, market app binaries, or generated run folders.
- Claim device validation only when actual device evidence exists.
- Preserve compatibility; document a justified interface/behavior change.

## Change and review discipline

Stabilize confirmed issues before major features. Preserve working functionality
and existing CLI flags/exit codes. Separate functional fixes from documentation
changes in logical commits. Add focused regressions for confirmed bugs; never
weaken evidence checks merely to make tests pass.

Source comments distinguish current behavior from known defects. Update those
notes only after implementing and verifying a fix. Keep JSON configuration valid;
explanations belong in CONFIGURATION.md or existing informational notes fields,
not JSON comments. TOOL_MANIFEST feature flags describe intent, not test proof.

Use a working project `.venv` and record actual full-suite/error/skip results.
Compilation, synthetic fixtures, mocked tests, live Appium, virtual devices, and
physical-device evidence are separate. Do not claim a green suite when dependencies
or test imports fail. SDK modules remain real; use scoped mocks and run each test module independently.

For documentation-only edits, verify executable Python ASTs and runtime configuration
remain unchanged, parse JSON, and compile. Do not silently fix behavior in a comment
pass. Explicit scenario mode does not automatically apply crawler safe-mode policy.

The current review PR is linked in DEVELOPER_GUIDE.md. Review the exact current
head, independently verify findings, and return severity/file/line/trigger/tests.
Creating a PR is not proof that local Claude received or completed a review.
