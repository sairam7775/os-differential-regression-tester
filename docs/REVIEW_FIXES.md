# Review stabilization record - 2026-10-14

Claude completed the baseline audit in [PR #1](https://github.com/sairam7775/os-differential-regression-tester/pull/1)
at 7d9739ed7dc071e97730f52bbf7d1db14810433d: 12 inline comments plus four
overlapping Codex bot comments. Fixes are in [PR #2](https://github.com/sairam7775/os-differential-regression-tester/pull/2),
targeting main. Claude re-reviewed a85fb29 and confirmed most earlier fixes; the
four follow-ups below are addressed in the new revision. Exact-head approval and
physical-device acceptance remain pending; audit threads stay open for verification.

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
| [High hardware mistaken for OS](https://github.com/sairam7775/os-differential-regression-tester/pull/1#discussion_r4266471366) | Known release/API/patch; builds qualify only on verified matching hardware | Samsung/Pixel model-specific builds invalid; same-model incremental and patch changes valid |
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
  XML, nested metadata, errors, traces, summaries, and retained local server logs. Custom
  input-rule values, expanded scenario inputs, and virtual target IDs also reach
  server-log sanitization rather than relying only on default environment names.
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
  The version probe now resolves Windows npm.cmd before invoking it, fixing a
  locally reproduced false missing-npm result.
- Removed global SDK stubs. CI installs real dependencies, serializes real Appium
  capabilities, compiles, runs the suite and each module independently, and checks CLI arguments.

## Claude re-review of a85fb29

The [completed re-review](https://github.com/sairam7775/os-differential-regression-tester/pull/2#pullrequestreview-5517326153)
confirmed child-caption safety, prohibited variants, Settings isolation, secure
input, valid XML redaction, and lock lifecycle. It raised four follow-ups:

| Finding | Assessment and response | Focused coverage |
| --- | --- | --- |
| [High replay aborted by any unruled field](https://github.com/sairam7775/os-differential-regression-tester/pull/2#discussion_r4270297898) | Agree. Continue navigation past unruled plain fields, retain blockers, and keep coverage partial. Refused secrets or missing baseline-filled input IDs still abort. Record stable requiredInputs without values. | Search plus Details replays; baseline reaches child; candidate intermediate blocker survives; missing/vanished/secure prerequisites fail; successful prerequisite fills replay |
| [High model-specific builds still count as OS](https://github.com/sairam7775/os-differential-regression-tester/pull/2#discussion_r4270297909) | Agree. Different/unverified models use release/API/patch only. Build ID/incremental require verified matching manufacturer/model. Persist qualifying fields/evidence. | Samsung S23/S24 incrementals and Pixel A1/F1 suffixes invalid; same-model incremental valid; missing/unknown hardware invalid; cross-model patch difference valid |
| [Medium mandatory rules block navigation](https://github.com/sairam7775/os-differential-regression-tester/pull/2#discussion_r4270297922) | Agree for generic order/status words. Shipped policy allows Order history, Sort order, In order to continue, Updates, Last updated and Recently removed. Each caption still blocks bare Order and purchase imperatives. Retain conservative hardware/state-mutation blocking for Connected devices, Print preview, Printer status and Remove from favourites under the business rules. | Explicit label outcome table with shipped policy; status-bearing card navigation; dangerous child/live caption; custom broad rules remain optional, denies win |
| [Medium default text/value noise](https://github.com/sairam7775/os-differential-regression-tester/pull/2#discussion_r4270297931) | Agree. Normalize known freshness age/clock/date values using narrow shipped/default patterns. Reject blanket number/date normalization because it hides meaningful regressions. Explicit [] disables defaults; original sanitized text remains in artifacts. | Relative time/clock/date noise ignored; count/price/version/ordinary-date/status-prefix changes and missing controls preserved; opt-out works |

These responses add 22 methods (18 pure replay/OS/policy fixtures and four real
hierarchy-comparison fixtures). Timing, visual noise, sync-freshness semantics,
localized captions, and ambiguous hardware surfaces remain app-specific. Use
explicit assertions or opt out when a freshness timestamp is meaningful evidence.
No safe-mode exception permits pairing, printing, firmware, purchases or destruction.

## Actual validation

Behavior commit 25cdb05f22aa479a4c8c33094ebc94b6c4ade112 passed
[CI run 38563111100](https://github.com/sairam7775/os-differential-regression-tester/actions/runs/38563111100).
There are 126 test methods across six modules, compared with 38 in the import.

| Environment | Full suite | Independent modules, compile, CLI argument paths |
| --- | --- | --- |
| Ubuntu/Python 3.11 | 126 run; 125 passed, 1 Windows-only skip; zero errors/failures | Passed |
| Ubuntu/Python 3.14 | 126 run; 125 passed, 1 Windows-only skip; zero errors/failures | Passed |
| Windows/Python 3.11 | 126 run; 125 passed, 1 POSIX permission skip; zero errors/failures | Passed |
| Windows/Python 3.14 | 126 run; 125 passed, 1 POSIX permission skip; zero errors/failures | Passed |

Local help/argument paths for every CLI command passed. A real doctor invocation
now recognizes npm 11.16.0 and exits 1 for missing Appium, ADB, JAVA_HOME, and its
UiAutomator2 doctor prerequisite; those checks do not perform a device run.

The first CI run exposed a Windows report-test decoding failure; it now reads UTF-8
HTML explicitly. Capability tests executed using installed Appium, without global
stubs. CI also checks the final documentation head; consult PR #2 checks for its SHA.

Restricted local Windows/Python 3.14.7 full discovery loaded 81 entries: 78 methods
passed, three discovery errors (Pillow unavailable in test_hardening, test_regressions,
and test_review_artifacts), exit 1. Independent market tests (15), review-fix tests
(45), re-review regressions (18), and compile passed. Installation remains blocked locally; this is not a local
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
- OS identity arrays retain five components for recording/post-run monitoring.
  Build components qualify as difference evidence only for verified matching hardware.
  Differing/unknown models need known release/API/patch difference.
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
