# Automatic discovery and replay

Both `auto-run` and `market-run` use `osdiff.crawler`. Policy and limits are
documented in [configuration](CONFIGURATION.md); persisted graph/trace fields
are documented in [artifacts](ARTIFACTS.md).

## Actual algorithm

1. Start a reusable target-specific Appium session.
2. Pop a baseline action path from a breadth-first queue, initially the empty path.
3. Terminate/reset/activate the target, then replay the path from launch.
4. Before each action, attempt configured input filling; after it, check foreground.
5. Capture hierarchy/context and fingerprint them; discard previously visited states.
6. For a first-seen state, fill known inputs, discover/filter/sort/cap actions, and save a checkpoint.
7. Queue child paths unless depth/other limits stop exploration.
8. Persist graph/summary, then replay one retained path per baseline screen on candidate.

One driver is reused per phase. Replay failure closes/recreates it. Session
creation and capture failures can still escape outside replay-error handling.

## State and action identity

Fingerprinting uses configured hierarchy attributes, normalized dynamic patterns,
and foreground context. It includes text/value by default. iOS context currently
includes transient PID, so relaunch may create duplicate state identities.
Fingerprinting also precedes input filling while capture can follow filling;
these identities/artifacts need alignment during stabilization.

Tap actions contain label, ordered locator candidates, ordinal, and bounds.
Ordinals are counted after safety filtering, while replay indexes unfiltered
live locator matches. This can select Print for a retained Settings action when
they share an ID. Fallback locators may have different match sets. Do not regard
the action record or keyword check as proof of safe live resolution.

The graph retains first-seen paths and queued `from` edges; it does not reliably
record edge destinations or duplicate-state outcomes. Candidate `reproducedScreens`
means captured checkpoints, not verified destination equivalence. Candidate
fingerprints are stored as metadata and not directly enforced by comparison.

## Policy and incomplete coverage

Deny patterns win over allowed words. Blocked controls and unresolved inputs at
discovered states, action truncation, baseline replay failure, depth/queue/screen/
path limits, parse failure, and branched non-deterministic baseline reset force
PARTIAL. Partial coverage is supplied to the report and yields INVALID/exit 3.

Current intermediate replay input blockers and candidate input/reset evidence are
not fully promoted into validity. Candidate missing checkpoints can score as
regressions, but that does not repair incomplete baseline evidence. Positive
coverage claims must address both sides and all explored/blocked/frontier actions.

## Supported surface and limitations

Native control heuristics cover taps, fields, tabs/cells/buttons by type, and a
whole-window downward swipe when scrollable content is recognized. There is no
automatic back action, container-specific upward/horizontal traversal, scroll-end
proof, or full custom/WebView interaction support. Fixed settling sleeps and
dynamic data can affect snapshots. Built-in system packages are always allowed;
configuration adds packages rather than removing the built-ins.

Printing, reprinting, Bluetooth pairing/connections, firmware, purchases, and
destructive operations remain outside automatic safe-mode validation.
