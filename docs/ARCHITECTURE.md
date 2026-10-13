# Architecture — v0.5 Hardened

```text
                SAME MARKET APP VERSION + BUILD
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
      Baseline physical phone          Candidate physical phone
      old OS/build                     new OS/build
              │                               │
              └───────────────┬───────────────┘
                              ▼
              Provenance + Environment Gate
          app/build + market origin + OS identity
          hardware + locale/display/orientation
                              │
                        PASS only
                              ▼
                 Deterministic Reset Layer
       Android pm clear / iOS reset hook / simulator reinstall
                              │
                              ▼
                  Baseline BFS Discovery
             hierarchy + visible text + app context
                              │
                     Navigation Graph
                              │
                              ▼
                  Candidate Path Replay
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
         Visual diff      UI-tree diff     Behavior/timing
             └────────────────┼────────────────┘
                              ▼
                    Fail-closed Reporter
             PASS / REVIEW / FAIL / INVALID
```

## Coverage validity

Coverage is not inferred merely from the number of screenshots. `COMPLETE_WITHIN_POLICY` requires:

- deterministic branch reset for branched exploration;
- no baseline replay failures;
- no blocked/unknown required inputs;
- no blocked safe-mode actions;
- no action truncation;
- no depth/screen/path limit exhaustion.

Candidate path failures are regressions rather than baseline-coverage invalidity.

## Session lifecycle

v0.5 reuses one Appium session per crawl/replay phase and resets/relaunches the target app between paths. A broken session is discarded and recreated. This avoids hundreds of real-device WDA/UiAutomator2 session startups.

## Foreground boundary

After launch and every action, the active package/bundle is verified. The target app and explicitly configured OS system surfaces are allowed. Unknown external applications terminate the branch.

## Data protection

Captured hierarchy and reports are local only. POSIX artifacts use owner-only permissions. Configured credential values are redacted from hierarchy XML; persisted real-device IDs are masked/hashed. Optional screenshot regions can be blacked out before storage.
