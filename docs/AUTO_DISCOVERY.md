# Automatic discovery and replay

`auto-run` and `market-run` share `osdiff.crawler`. [CONFIGURATION.md](CONFIGURATION.md)
describes policy; [ARTIFACTS.md](ARTIFACTS.md) describes persisted evidence.

## Algorithm and ownership

1. Pop a baseline path from a breadth-first queue, initially empty.
2. Create/reuse a target-specific session, terminate/reset/activate, and verify foreground.
3. Before each replay action, verify foreground and fill permitted inputs. Unruled plain fields stay empty and recorded; refused secrets or missing baseline-filled prerequisites fail the path.
4. Refresh source and native identity, validate live safety, execute once, and verify foreground afterward.
5. Fill inputs at the destination, refresh hierarchy/context, then fingerprint the captured state.
6. Skip duplicate fingerprints while retaining blockers. For a new state, discover/filter/cap actions and capture sanitized evidence.
7. Queue child paths with stable IDs of baseline-filled inputs required for replay, unless depth/other limits stop exploration.
8. Persist graph/summary, then replay one retained path per baseline screen on the candidate.

A session is reused per phase and closed/recreated after replay/state failure.
Creation/reset/action/capture failures are recorded, and phase exit attempts quit.
Reset status is tri-state: DETERMINISTIC, NON_DETERMINISTIC, UNKNOWN. An action
failure does not erase evidence that its reset succeeded.

## Safe control identity

Fingerprints use configured hierarchy attributes and normalized dynamic patterns,
plus stable package/activity/bundle context. PID is excluded and input filling
precedes fingerprinting. Overbroad dynamic patterns can still merge meaningful states.

Tap actions carry native identity, descendant captions, per-locator occurrence,
and bounds. Occurrences count all matching source controls before filtering.
Replay resolves the fresh hierarchy and validates live attributes, enabled state,
and descendant safety before clicking once. Unverified legacy records and unsafe
or changed controls fail. Bounds are informational; no coordinate fallback is used.

Mandatory safe-mode rules cover prohibited hardware, payment, and destructive
labels plus their common inflections. Generic order/status words are not
mandatory; individual captions still block bare Order and purchase imperatives.
Order history, Updates, Recently removed, and Last updated cards are navigable
with shipped policy. Connected devices, Print preview, Printer status, and
Remove from favourites remain conservatively blocked. Custom rules add to the floor.
Only target-app controls and narrow Android/iOS permission dialogs may be traversed.
Settings/installers/arbitrary external apps are rejected even if custom-listed.
Secret rules require native secure-field evidence before typing; unknown or
unrelated fields remain blocked. Keep `safeMode` enabled for market testing.

## Coverage and remaining limitations

Blocked controls/inputs, truncated actions, failed/missing paths, capture/parse
failures, exhausted limits/frontiers, or branched unknown/non-deterministic reset
on either target force PARTIAL. Reports then yield INVALID/exit 3 even when some
captured checkpoints agree. COMPLETE_WITHIN_POLICY is confined to observed scope.

The graph keeps first-seen paths and queued source edges, without reliable resolved
destinations or duplicate-edge outcomes. Candidate reproducedScreens counts captures,
not semantic equivalence. Comparison examines matched artifact pairs separately.

Native heuristics support taps, fields, tabs/cells/buttons, and one whole-window
downward swipe. There is no automatic back action, scoped up/horizontal traversal,
scroll-end proof, or complete custom/WebView support. Dynamic data and fixed waits
can affect snapshots. Localized/new permission surfaces fail closed and need
focused fixtures before extending recognition. Physical validation remains pending.
