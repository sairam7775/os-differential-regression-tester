# Review stabilization record - 2026-10-14

Claude completed the baseline audit in [PR #1](https://github.com/sairam7775/os-differential-regression-tester/pull/1)
at 7d9739ed7dc071e97730f52bbf7d1db14810433d: 12 inline comments plus four
overlapping Codex bot comments. Fixes are in [PR #2](https://github.com/sairam7775/os-differential-regression-tester/pull/2),
targeting main. Claude has not yet approved this follow-up diff; original audit
threads remain open for independent verification.

## Review mapping

All rows are implemented with synthetic regression fixtures. They do not establish
physical-device safety. Comment IDs link to the original findings.

| Claude finding | Implementation | Regression evidence |
| --- | --- | --- |
| [Critical child-caption bypass](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471335) | Discovery includes descendant captions; live descendants rechecked before click | Nested Android rows, iOS cells, changed live captions |
| [High prohibited variants](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471349) | Mandatory deny floor, token normalization, common inflections, custom additions | Unpair/Pairing, Disconnect/Connecting/Connected, Payment/Purchases, Checkout/Reorder, clear storage, force stop, install/update |
| [High system traversal](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471354) | Target or narrow permission dialog required; custom packages cannot widen boundary | Settings/installer rejection, unrecognized permission rejection, partial crawl without system edges |
| [High PIN leakage](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471357) | Word-boundary password rule plus secure native field validation | Shipping/shopping/spinner/typing/plain PIN never receive password |
| [Secure flag ignored](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471360) | Secret/secure rules require secure source and live attributes | Secure PIN succeeds; secret rule on ordinary field blocks |
| [High hardware mistaken for OS](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471366) | Known common release/API/patch/build ID/incremental; hardware fingerprint portions excluded | Same OS/different models invalid; patch/build difference valid; missing values invalid |
| [XML redaction invalidates evidence](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471371) | Decode/replace/serialize XML, recursively sanitize artifact strings | Escaped credentials parse; malformed captures stay invalid; metadata/IDs sanitized |
| [Medium reset defense](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471377) | Simulator reinstall rejects preinstalled runtime; market options reject binary | No simctl call, real Appium capabilities omit app binary |
| [Low reset misreported](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471386) | Preserve actual reset result; null means UNKNOWN | Successful reset plus failed action stays deterministic |
| [Low empty lock stuck](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471389) | Kernel-owned descriptor; safe Windows legacy query; finally release | Empty/corrupt reusable, second process excluded, success/error/cancel cleanup, no Windows os.kill |
| [Low private emulator logs](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471392) | Run directory, safe unique filenames, POSIX permissions | Requested log directory and POSIX mode 0600 |
| [README caveats](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471399) | Explain current boundaries and remaining validation limits | Parsed links/config, executable AST unchanged by explanatory edits |

The four Codex comments overlap child captions, prohibited inflections, Settings,
and PIN leakage; the same fixes cover them.

## Additional baseline fixes

- Per-locator occurrences count all native matches before filtering. Fresh identity,
  live enabled state, and descendant safety stop duplicate-ID/fallback/stale control
  mistakes. Click once; no coordinate or gesture retry after uncertain outcomes.
- Strict nonempty summaries reject malformed JSON, duplicates, and bad status records.
  Checkpoint assertions must be boolean; timings numeric, finite, and nonnegative.
  Failed baseline actions/assertions, empty results/hierarchy, bad XML/images, and
  invalid state evidence yield INVALID. Missing candidate actions are critical regressions.
- Continued scenario failures and false assertions keep status failed. Known configured
  environment values, expanded inline input values, and target IDs are sanitized in
  XML, nested metadata, errors, traces, summaries, and retained local server logs.
- Both devices contribute reset/input evidence. Every failed or missing candidate
  branch is partial. Source/capture failures preserve prior successful states.
  Fingerprints follow input filling and exclude transient process IDs.
- iOS UDIDs must appear in Xcode physical enumeration. Re-probe app/OS/target identities
  after market capture; updates, changes, or unavailable probes invalidate provenance.
  Exact app version/build remains mandatory; preinstalled runtimes reject app binaries.
- Deferred optional imports keep help/prerequisite paths usable. Appium requires its
  readiness flag, honors local address/base path, closes failed-spawn handles, and
  terminates/waits after timeout. External servers remain operator-owned. Shared
  SDK-root/PATH ADB lookup and explicit PowerShell Python exit checks fix setup gaps.
- Removed global SDK stubs. CI installs real dependencies, serializes real Appium
  capabilities, compiles, runs the suite and each module independently, and checks CLI arguments.

## Actual validation

Behavior commit 45bc9662610284d1eeafa924188d9ace5fa75691 passed
[CI run 38552550322](https://github.com/sairam7775/os-differential-regression-tester/actions/runs/38552550322).
There are 103 test methods across five modules, compared with 38 in the import.

| Environment | Full suite | Independent modules, compile, CLI argument paths |
| --- | --- | --- |
| Ubuntu/Python 3.11 | 103 run; 102 passed, 1 Windows-only skip; zero errors/failures | Passed |
| Ubuntu/Python 3.14 | 103 run; 102 passed, 1 Windows-only skip; zero errors/failures | Passed |
| Windows/Python 3.11 | 103 run; 102 passed, 1 POSIX permission skip; zero errors/failures | Passed |
| Windows/Python 3.14 | 103 run; 102 passed, 1 POSIX permission skip; zero errors/failures | Passed |

The first CI run exposed a Windows report-test decoding failure; it now reads UTF-8
HTML explicitly. Capability tests executed using installed Appium, without global
stubs. CI also checks the final documentation head; consult PR #2 checks for its SHA.

Restricted local Windows/Python 3.14.7 full discovery loaded 62 entries: 59 methods
passed, three discovery errors (Pillow unavailable in test_hardening, test_regressions,
and test_review_artifacts), exit 1. Independent market tests (15), review-fix tests
(44), and compile passed. Installation remains blocked locally; this is not a local
full-suite pass. [BASELINE_ASSESSMENT.md](BASELINE_ASSESSMENT.md) preserves original results.

No physical devices, emulators, simulators, printers, or live Appium sessions were
tested. Real SDK serialization and scoped mocks do not establish device launch,
transport, signing, reset effectiveness, or hardware-operation safety.

## Compatibility and remaining work

CLI flags, exit meanings, scenario schema, exact build gate, and version 0.5.0 remain.
These deliberate safety tightenings are documented:

- Settings/installers/photo/file apps and arbitrary custom external packages stop
  automatic traversal. Only recognized permission dialogs are supported.
- Empty custom denies retain the mandatory safe-mode floor. Explicit unsafe mode
  disables deny filtering and must not be used for market sign-off.
- Old graphs without native identity fail closed; regenerate instead of using coordinates.
- Password/PIN/token/secret input rules require secure fields; plain/unknown fields block.
- Hierarchy defaults include text/value. Normalize only known dynamic noise. Invalid
  old checkpoint states without boolean assertions/valid timings are rejected.
- OS identity arrays now contain five OS-only components. Hardware/missingness is not OS evidence.
- The empty lock file remains after release; kernel ownership determines activity.

Next: independent PR #2 review, dedicated two-phone Android acceptance, then iOS
when macOS/signing/two iPhones exist. Remaining work includes graph destinations/
duplicate outcomes, scoped scrolling/back/custom views, localized permission dialogs,
dynamic content, repeated timing samples, hardware/backend confounders, and report
detail/scope. reproducedScreens counts captures, not semantic destination equivalence.
Environment values missing on one device are skipped; reset hooks remain trusted.

Windows inherits artifact ACLs; POSIX permissions are best-effort. Screenshot privacy
requires storage masks and dedicated non-personal data. Known-value redaction does
not recognize all personal content or control external Appium server logs.
