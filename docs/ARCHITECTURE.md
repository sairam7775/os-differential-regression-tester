# Architecture and ownership - v0.5.0

## Market-mode flow

```text
CLI/config -> start or reuse ready Appium -> inspect two physical targets
 -> gate exact app/version/build, origin, known OS difference, model/environment
 -> persist masked provenance; invalid gate writes INVALID and exits 3
 -> reset/launch baseline BFS -> reset/replay retained paths on candidate
 -> re-probe app, OS, and target identities; changed/unavailable evidence is INVALID
 -> compare artifacts -> combine coverage/provenance -> write HTML/JSON
 -> stop owned Appium and release our kernel run lock in finally
```

Virtual modes use `devices` to provision targets with the operator-supplied binary.
Market mode uses `market` probes and rejects supplying a binary to preinstalled
Appium options. It never replaces the target store installation.

## Resource ownership

| Resource | Owner and cleanup |
| --- | --- |
| Existing Appium server | External operator; the tool leaves it running |
| Locally started Appium | CLI; startup failure terminates/waits, command finally stops it |
| Process log handle | Parent closes after spawn, including spawn errors |
| Virtual target | `devices` handle and CLI phase finally; emulator logs are under private run directories |
| Scenario session | `run_scenario`; best-effort quit in finally |
| Crawl/replay session | Reused per phase, discarded after replay/state failure, closed at phase exit |
| Run lock | `main`; non-inherited descriptor with fcntl/msvcrt ownership, released in finally |
| Artifacts | Local run directory; positive retentionDays enables cleanup |

`replay_path` leaves supplied sessions to the caller. A created session closes on
failure and transfers on success. Creation, reset, action, source, and capture
failures are recorded as failed/incomplete evidence. Cleanup remains best-effort;
synthetic tests do not establish live Appium transport behavior.

## Interaction and reset boundaries

Each branch terminates/resets/activates the selected target. Android data clear
uses the explicit serial and preserves the binary. iOS relaunch is non-deterministic;
external reset hooks are trusted on exit zero. Simulator reinstall rejects market
runtimes even if a binary was accidentally supplied.

Foreground must be the target app or a narrowly recognized permission dialog.
Settings, installers, photo/file apps, and arbitrary external surfaces stop the path.
Custom allowances cannot widen this boundary. Permission surfaces expose only
recognized permission buttons, without scrolling or credential entry.

Tap identities include native attributes and descendant captions. Each locator
stores its own unfiltered occurrence. Replay refreshes source, resolves a unique
identity, checks live attributes/enabled state/descendant safety, and clicks once.
There is no coordinate or gesture retry after an uncertain click. Secret input
requires secure-field evidence in both source and live native attributes.

## Discovery and validity

Fingerprinting follows input filling and uses stable package/activity/bundle
context, excluding process IDs. First-seen paths represent states. Queued edges
still lack resolved destinations; candidate reproduced counts captures rather
than proven destination equivalence. Graph accuracy and richer traversal are future work.

Strict summaries/checkpoints reject malformed JSON, duplicate scenarios, bad
assertion/action records, failed baseline evidence, invalid XML/images, and empty
results. Missing candidate actions are critical regressions. Both targets contribute
reset/input evidence; every failed or missing branch forces PARTIAL. Report
precedence remains INVALID > FAIL > REVIEW > PASS. See [ARTIFACTS.md](ARTIFACTS.md).

## Privacy and remaining limitations

Known secrets and target IDs are sanitized in XML and structured artifact strings.
Provenance masks/hashes primary IDs. Optional storage screenshot masks run before
report copies; comparison ignore masks affect measurement only. POSIX 0700/0600
permissions are best-effort and Windows inherits ACLs. Dynamic personal data and
external server logs require operator-controlled storage and dedicated test data.
See [REVIEW_FIXES.md](REVIEW_FIXES.md) for tests and pending real-device acceptance.
