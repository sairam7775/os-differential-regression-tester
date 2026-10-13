# Architecture and ownership — v0.5.0

## Market-mode flow

```text
CLI + config
  -> start/reuse Appium
  -> inspect baseline and candidate physical devices
  -> validate app version/build, origin, OS identity, model/environment policy
  -> persist masked provenance
  -> if gate invalid: write INVALID report; exit 3
  -> reset + launch + baseline BFS discovery
  -> replay baseline paths on candidate, preserving checkpoint names
  -> compare screenshots, hierarchy, execution, assertions, action timing
  -> combine comparison with coverage/provenance; write HTML/JSON
  -> stop owned Appium process; translate status to exit code
```

Virtual modes provision baseline then candidate emulators/simulators using
`devices`; scenario mode invokes `runner`, automatic mode invokes `crawler`.
Market mode uses `market` probes instead and omits the Appium app capability.

## Resource ownership

| Resource | Owner | Cleanup |
| --- | --- | --- |
| Existing Appium server | External operator | Tool does not stop it |
| Locally started Appium process/log | CLI start/stop helpers | Command-level finally calls stop; startup-failure cleanup needs hardening |
| Virtual emulator process/simulator | `devices` handle and CLI phase | Stop in phase finally; Android preparation errors attempt cleanup |
| Scenario Appium session | `run_scenario` | Best-effort quit in finally |
| Discovery/replay Appium session | Crawl/replay phase | Reuse per phase; close/recreate after replay failure; close at phase exit |
| Run lock | CLI `main` | Acquired for three run modes; currently no release call and unsafe Windows liveness probe |
| Artifacts | Local run directory | Retention deletes old directories only when enabled |

`replay_path` leaves a supplied session to its caller on error; sessions it
creates are closed on replay error and transferred on success. Session creation,
capture, and source failures can still escape before a final report is persisted.

## Reset and foreground boundaries

Before each queued path, terminate the target, execute its reset strategy, activate
it, settle, and require a known app/system foreground. Android data clear uses the
explicit runtime serial. Real iOS relaunch returns non-deterministic reset evidence.
Simulator reinstall changes a virtual app installation and must remain unavailable
to market-installed binaries. External hooks are trusted on exit zero.

Configured system packages extend built-in allowances; they do not replace them.
The `after_activation` argument currently does not impose a stricter target-only
check. Unknown foreground identity fails, but allowed system surfaces may satisfy
the launch check. See [baseline assessment](BASELINE_ASSESSMENT.md).

## Discovery and comparison are separate

Baseline paths are explored breadth-first from reset state. First-seen UI/context
fingerprints retain one representative path. Candidate replay captures artifacts
for those paths under the baseline checkpoint IDs. Its "reproduced" count currently
means capture success, not destination equivalence.

Comparison joins artifacts by scenario/checkpoint and assigns the maximum applicable
risk score. INVALID is evidence validity; FAIL/REVIEW are scored differences. Report
precedence is INVALID > FAIL > REVIEW > PASS. The CLI uses invalid/high-risk counts
for its exit decision. See [artifact fields](ARTIFACTS.md).

## Intended validity and current gaps

Sign-off requires an unchanged matched app build, verified OS difference, valid
baseline evidence, deterministic branched reset on both devices, valid artifacts,
no unexplored/blocked/failed coverage, and no High/Critical regression.

The implementation already invalidates explicit baseline replay failures, blocked
actions/input at discovered states, truncation, exhausted limits, malformed XML,
and supplied partial coverage. It does not yet enforce every prerequisite:
malformed JSON, failed baseline assertions, intermediate replay inputs, candidate
reset evidence, missing OS fields, and post-run app identity need stabilization.

## Privacy

Artifacts remain local; HTML embeds paths to local report image copies. POSIX
directory/file permissions are best-effort 0700/0600, without Windows ACL changes.
Primary provenance device IDs are masked/hashed. Optional screenshot masks run
before storage, while comparison ignore masks affect measurement only. Literal
hierarchy redaction and unsanitized structured fields are known defects.
