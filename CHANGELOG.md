# Changelog

## Unreleased — Developer documentation and comments

- Added module/helper contract docstrings and test-module scope notes without changing executable Python statements.
- Added AGENTS.md, CLAUDE.md, developer/configuration/artifact guides, and a complete reference for the shipped configuration fields.
- Updated README, architecture, quick start, market, discovery, scenario, and handoff documentation to distinguish intended guarantees from unresolved baseline defects.
- Clarified example configuration/scenario notes and added informational manifest validation/documentation metadata; runtime settings, dependency ranges, CLI flags, and version remain unchanged.
- Documented historical test errors, pending Claude review, and absence of device evidence. These explanatory updates are not functional fixes.

## v0.5.0 — Fail-closed hardening

- Baseline crawler replay failures now force `PARTIAL` coverage.
- Action truncation (`maxActionsPerScreen`) is recorded and forces `PARTIAL`.
- Deny/safety rules now always override permissive words.
- Discovery fingerprints include normalized visible text/value plus foreground app context so text-only pages are not collapsed.
- Automatic checkpoints now persist baseline/candidate action traces; action failures and timing regressions are compared.
- Missing action ordinals no longer fall back to the first matching control.
- App activation is verified; unknown external foreground apps stop a path. Recognized system surfaces are configurable.
- Android market crawling clears target app data between branches while preserving the market installation.
- iOS real-device branch isolation is fail-closed: relaunch-only crawling is `PARTIAL` for branched exploration unless a deterministic reset command is configured.
- Automatic crawler reuses Appium sessions and resets app state between branches, greatly reducing session startup overhead.
- `PARTIAL` coverage now makes the HTML/JSON summary `INVALID`; CLI and report status cannot disagree.
- Malformed/missing accessibility hierarchy is `INVALID` instead of being treated as identical.
- Fixed iOS `mobile: listApps` argument to `returnAttributes`.
- Improved iOS model detection and fail-closed same-model enforcement when identity is generic/unverified.
- OS identity now includes build/security-patch information when available, enabling patch-level differential testing.
- Added environment preflight comparison for locale/timezone/display/orientation facts when available.
- Added mode-aware `doctor --mode virtual|market --platform ...`.
- Added single-run lock and unique run directory IDs.
- Added subprocess timeouts for SDK/ADB/simctl operations.
- Optimized visual metrics using Pillow histogram/stat operations instead of a Python per-pixel loop.
- Hardened artifacts: owner-only POSIX permissions, hierarchy secret redaction, device-ID masking/hashing, optional screenshot masking and retention cleanup.
- Removed the unused `requireExactAppVersionAndBuild` switch; exact matching is an invariant.
- Expanded regression tests for the hardening findings.

## v0.4.0 — Real physical devices + market builds

- Added `market-run` and `list-real-devices`.
- Added strict store-build provenance gate and physical-device automatic discovery/replay.

## v0.3.0 — Automatic discovery

- Added breadth-first UI-state discovery and baseline navigation graph replay.

## v0.2.0 — Reliability hardening

- Prevented false PASS on failed/incomplete comparisons and hardened device targeting/reporting.
