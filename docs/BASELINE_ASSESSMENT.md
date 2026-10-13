# v0.5.0 baseline assessment

Reviewed on 2026-10-14. Source baseline: commit
`3e33cb26e2690305b2b6c4f6498fb0d93fedd65e` in
`sairam7775/os-differential-regression-tester`.

## Import and validation evidence

The supplied hardened ZIP contained 33 files, including VERSION `0.5.0`.
Its outer directory was removed during import. Source and documentation bytes
were preserved; the existing repository `.gitignore` was retained because it
also excludes environment files and Python bytecode. Shell scripts have Git
mode `100755`. All 33 imported blob hashes and modes were checked against the
GitHub tree before publishing. Existing repository history was preserved.

The review covered README, CHANGELOG, all documentation, all eight Python
source files, all three test modules, configuration, scenarios, and scripts.
No functional code changes have been made in this assessment.

Developer comment/documentation follow-up: module/helper docstrings, the README,
configuration/scenario explanations, artifact contracts, and agent handoff guidance
now describe these limitations directly. Read `DEVELOPER_GUIDE.md`,
`CONFIGURATION.md`, and `ARTIFACTS.md` alongside this historical assessment.
Executable behavior remains the imported baseline; no issue below is marked fixed.

### Actual automated test results

Environment: Windows, Python 3.14.7, project-local virtual environment.

Command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Result: exit code **1**, `Ran 17 tests in 0.019s`, `FAILED (errors=3)`.
There were **14 passing test methods**, one test-method error, and two
module-discovery errors. The source contains **38 test methods**; this was
not a successful execution of the full suite.

- `test_hardening` failed to import because Pillow (`PIL`) was unavailable.
- `test_regressions` failed to import for the same reason.
- `test_ios_list_apps_uses_return_attributes_contract` errored while importing
  `appium.options` through `osdiff.runner`. Its fake top-level Appium module
  does not supply those submodules when run without the other module's stubs.

Installing `requirements.txt`, installing Pillow separately, and retrying
Pillow against the explicit PyPI index all failed with no matching
distribution available in this environment. This is an environment blocker;
it does not establish that the declared package versions are unavailable on
PyPI generally.

`python -m compileall -q osdiff.py osdiff tests` passed. CLI `--help` failed
before argument parsing because the CLI eagerly imports the Pillow-dependent
comparison module. Successful compilation is not CLI or Appium validation.

No `adb`, `appium`, or `xcrun` executable was found on PATH. No Android or iOS
real-device testing, emulator testing, simulator testing, or live Appium
session testing was performed. Claude review is pending the stabilization
changes requested in the handoff.

## Architecture and working foundations

The CLI owns orchestration, local server startup, run directories, and exit
codes. `devices` provisions virtual targets; `market` probes and gates physical
devices; `runner` executes explicit scenarios; `crawler` discovers baseline
states and replays paths; `compare` scores artifacts and writes reports;
`fsutil` centralizes artifact handling.

Preserve the existing market runtime's omission of the Appium `app`
capability, exact version/build checks, Android app-data reset, deny-rule
precedence, partial-coverage invalidation, HTML escaping, duplicate hierarchy
counts, explicit target UDIDs, and session cleanup in the main run phases.
These are useful foundations, although they require fuller tests.

The main architectural weaknesses are loosely validated dictionaries,
validity inferred from incomplete artifacts, safety inferred from one
discovered label rather than the resolved live control, and privacy applied
to only selected artifact channels. The large CLI also couples prerequisite
commands to comparison dependencies.

## Prioritized findings

### Priority 1: stabilization, safety, and truthful results

1. **Critical: a safe action can resolve to a blocked control.**
   `crawler.discover_actions` assigns ordinals after filtering unsafe and
   disabled controls, while `_find_for_action` indexes the full live locator
   result. In a synthetic hierarchy with Print then Settings sharing an ID,
   Print is blocked but Settings gets ordinal zero and resolves to Print.
   Locator fallback also applies one ordinal to different match sets. Action
   resolution must prove the live target matches the intended control and
   reapply safety before every click and gesture fallback.
2. **Critical on Windows: the run-lock liveness probe can kill a process.**
   `_pid_alive` calls `os.kill(pid, 0)`. Python documents that Windows uses
   `TerminateProcess` for signals other than its two console-control signals.
   Replace this with a non-destructive Windows process check. Do not exercise
   this probe against a live application to reproduce the issue. Source:
   [Python os.kill documentation](https://docs.python.org/3.14/library/os.html#os.kill).
3. **High: the CLI never releases its run lock.**
   `main` acquires the lock but has no call to `_release_run_lock` and no
   cleanup `finally`. Add cleanup on success, failure, and cancellation;
   handle stale locks without racing another owner or trusting PID reuse.
4. **High: secret redaction corrupts XML and misses other artifact channels.**
   `fsutil.redact_values` inserts literal `<REDACTED>` inside attribute values,
   making captured XML invalid. Encoded secret values can also escape literal
   replacement. Traces, locator labels, assertions, errors, and scenario
   summaries are persisted without equivalent sanitization. Device IDs can
   enter reset-command errors despite provenance masking. Screenshot masking
   is opt-in; Windows artifact ACL enforcement is absent. Redact parsed XML
   and all persisted structured/string fields while preserving valid syntax.
5. **High: invalid execution evidence can be treated as valid.**
   `compare._load` silently replaces malformed JSON with defaults;
   `_execution_results` returns no errors for two malformed summaries. Bad
   checkpoint state becomes an empty dictionary. Baseline assertion failures
   are not invalidated by `_behavior`; missing candidate action records are
   ignored because only the common trace prefix is compared. A continued
   scenario action failure can still finish with status passed, and failures
   after the final checkpoint are not necessarily compared. Require complete,
   well-formed evidence and distinguish baseline invalidity from candidate
   regressions.
6. **High: candidate replay evidence does not control validity completely.**
   `coverage_summary` uses only baseline reset isolation, even when candidate
   replay reports non-deterministic resets. Blocked inputs on intermediate
   replay screens are recorded but do not invalidate the crawl. Candidate
   blocked inputs are not promoted into result validity. The reproduced
   counter means a checkpoint was captured, not that the intended screen was
   reached. Record both devices' reset/coverage prerequisites and validate
   replay outcomes independently of cosmetic differences.
7. **High: market identity checks can accept missing OS evidence.**
   A known baseline OS tuple and an empty candidate OS tuple are different, so
   `validate_market_pair` accepts that condition when other fields match.
   Missing fields must not establish an OS difference. Compare verified
   common OS fields and require positive evidence. iOS physical-device status
   is also assumed when simulator metadata is absent. App version/build is
   checked only before crawling; verify it again at completion to catch store
   auto-updates. Keep the explicit limitation of iOS store-origin attestation.
8. **High: market reset configuration can select simulator reinstallation.**
   `_prepare_path` accepts `ios_simulator_reinstall` based on platform and
   `appPath`, without an explicit virtual-device/preinstalled check. Normal
   market runtimes omit `appPath`, but public helper input must not be enough
   to authorize replacing a market binary. Restrict reset strategies by mode
   before any device operation; external reset hooks require an explicit
   operator contract preserving the store-installed binary.
9. **High: baseline tests depend on global module stubs and import order.**
   `test_hardening` populates Appium/Selenium stubs in `sys.modules` even if
   real clients are installed but not yet imported. Subsequent tests can
   therefore exercise stubs rather than the installed capability classes.
   Scope fakes to individual tests, make each module independently runnable,
   and separately test the real client option serialization.

### Priority 2: real-device readiness

- Standardize ADB lookup. `devices.adb_path` honors SDK environment variables,
  whereas `market` and market resets primarily require ADB on PATH. Doctor
  can find ADB while market-run cannot use it.
- Add subprocess timeouts to virtual target listing; verify Appium readiness
  payloads rather than only HTTP 200. Validate base paths, address, and scheme
  before local startup, and clean up processes after startup failure.
- Inspect session creation, capture, source retrieval, reset, and quit failure
  paths with controlled mocks, then run physical-device acceptance tests.
  A failed screenshot return value is currently ignored; capture exceptions
  can abort before a useful final INVALID report is written.
- PowerShell setup checks npm/driver exit codes but does not explicitly check
  the Python venv/pip exit codes, so a failed Python setup may be reported as
  complete. Make every setup stage fail visibly.

### Priorities 3-5: discovery, analysis, reporting

- iOS state fingerprints include the process ID from activeAppInfo, so a
  relaunch can make the same screen appear new. Exclude transient context.
  Fingerprints are computed before input filling but saved with artifacts
  captured afterward; align state identity with captured state.
- Duplicate-state paths are discarded without recording their destination
  edges. The graph has queued outgoing edges but no reliable `to` state or
  action outcome. Add explicit explored, blocked, failed, and frontier state.
- Scrolling is one whole-window downward swipe, without container identity,
  upward/horizontal traversal, or scroll-end evidence. Back navigation is not
  an automatic action. Webviews and unlabeled/custom controls remain limited.
- Default comparison hierarchy attributes omit Android `text` and iOS
  `value`. A text-only synthetic hierarchy change produced ratio zero.
  Empty but well-formed hierarchies can also count as identical. Track
  meaningful content and control removals, with explicit dynamic-field rules.
- Timing uses wall-clock time, includes configured sleep, and measures one
  traversal per checkpoint. Use a monotonic timer and report sample/context
  limitations before treating small changes as regressions.
- Visual comparison resizes candidate screenshots and measures pixel ratios;
  hardware/layout/content differences remain confounders. Preserve original
  dimensions and add controlled noise fixtures before adjusting thresholds.
- HTML presents side-by-side screenshots, but does not fully expose recorded
  OS build/security-patch details, environment differences, or detailed
  blockers. The valid-checkpoint count includes INVALID checkpoints. Requested
  platforms skipped on an incompatible host are not shown in report scope.

## Isolated reproduction evidence

These standard-library probes exercised the original pure function bodies
and synthetic data. Appium/Pillow import statements were excluded only for
these isolated probes; no screenshots or devices were simulated as successful
end-to-end runs, and these probes do not replace the existing test suite.

```text
redaction_breaks_xml: True
safe_action_label: Settings resolved_control: Print
pid_changes_state_identity: True
failed_baseline_assertion_regressions: []
missing_candidate_action_regressions: []
malformed_summaries_execution_results: []
text_only_hierarchy_difference: 0.0
missing_candidate_os_identity_accepted: True
candidate_nondeterministic_reset_coverage: COMPLETE_WITHIN_POLICY DETERMINISTIC
main_lock_release_calls: 0
test_methods_in_source: 38
```

## Proposed implementation sequence

1. Restore a complete dependency installation and run all 38 baseline tests.
   Add Windows and macOS CI with independently runnable test modules. Record
   genuine failures before fixing them; do not weaken tests to get a PASS.
2. Commit safe live-control resolution with duplicate-ID, differing locator
   match-set, stale control, disabled control, and destructive-label tests.
3. Commit run-lock lifecycle fixes with non-destructive Windows liveness,
   stale-owner handling, and success/error/cancellation cleanup tests.
4. Commit syntax-preserving artifact redaction with escaped-value, JSON,
   error/trace, identifier, and screenshot-mask tests. Keep raw secrets out of
   retained test output and preserve existing POSIX permission behavior.
5. Commit fail-closed evidence handling: malformed/missing artifacts, baseline
   assertions, incomplete/failed traces, capture failures, both-device reset
   evidence, blocked replay input, and identical app/verified OS invariants.
6. Commit CLI/setup and session lifecycle stabilization. Verify help/doctor,
   listing, run, auto-run, and market-run argument/error paths without device
   side effects; use real client capability serialization plus scoped mocks.
7. Request Claude review of the stabilization diff, resolve actionable
   findings, and rerun relevant checks. No Claude review result is claimed yet.
8. Validate safe Android market-run on two physical devices with identical
   store version/build and verified different OS identity. Keep device evidence
   local/private and record the exact tested commit. Validate iOS only with
   macOS, two physical iPhones, valid signing, and honest reset semantics.
9. Improve discovery, regression analysis, and reporting in separate logical
   commits after stabilization, with updated README/architecture/changelog.

Keep existing CLI flags and exit-code meanings unless a compatibility change
is necessary and documented. Never replace market binaries, weaken exact
app-build matching, call skipped coverage complete, treat iOS relaunch as a
reset, or exercise printer/Bluetooth/payment/firmware operations in safe mode.

## Local execution instructions

From a normal terminal with Python 3.10+, supported Node/npm, Java, and Android
platform tools available:

```powershell
git clone https://github.com/sairam7775/os-differential-regression-tester.git
cd os-differential-regression-tester
.\scripts\setup-local.ps1
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\scripts\osdiff.ps1 doctor --mode market --platform android
.\scripts\osdiff.ps1 list-real-devices
```

Use `docs/QUICKSTART.md` and `docs/REAL_DEVICE_MARKET_MODE.md` for physical-device
preparation and market-run arguments. Android automatic discovery clears app
data between paths: use dedicated test devices/accounts. Until the critical
safe-control and Windows locking findings are fixed, treat this import as a
review baseline rather than a validated safe-mode release.
