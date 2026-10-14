# Developer guide and handoff

## What this project proves

The business question is whether an OS release/build/patch changes the behavior
of one unchanged production app build. Android/iOS and Fujifilm INSTAX companion
apps are the intended use cases. Compare equivalent test accounts/data and
environment settings; backend/hardware/content differences are confounders.

`market-run` is the production-oriented path and never supplies a target app binary.
`auto-run` and `run` are virtual-device development paths. Keep their provisioning
operations separate from physical market devices. Current results are limited by
the [baseline assessment](BASELINE_ASSESSMENT.md), not by the strength of a label
such as "hardened" or a feature flag in the informational manifest.

## Source map

| File/module | Responsibility | Main entry points |
| --- | --- | --- |
| `osdiff.py` | CLI, config, Appium process, orchestration, reports, exit codes | `main`, `market_run_cmd`, `auto_run_cmd`, `run_cmd` |
| `osdiff/devices.py` | Virtual target provision/identity/cleanup | `prepare_android`, `prepare_ios`, `stop_android`, `stop_ios` |
| `osdiff/market.py` | Physical probes, provenance gate, preinstalled runtimes | `probe_*_market_device`, `validate_market_pair`, `market_runtime` |
| `osdiff/runner.py` | Shared Appium capabilities and explicit scenarios | `_options`, `run_scenario`, `run_target` |
| `osdiff/crawler.py` | Discovery, reset/replay, native actions, graph artifacts | `crawl_baseline`, `replay_candidate_graph`, `coverage_summary` |
| `osdiff/compare.py` | Checkpoint/execution comparison and reporting | `compare_platform`, `write_report` |
| `osdiff/fsutil.py` | Artifact writing, POSIX permissions, masks/redaction | `write_json`, `write_text`, `mask_image_regions` |

The package `osdiff` and root script `osdiff.py` share a name intentionally:
run `python osdiff.py ...`; internal imports use the package directory.

## Contracts to preserve

- A runtime dictionary identifies `udid`, optional `appPath`, package/bundle,
  `preinstalled`, reset strategy, and privacy settings. Market runtimes have no
  app binary and use `preinstalled=True`, `noReset=True`.
- `replay_path` returns `(driver_or_none, trace, error_or_none, deterministic)`.
  Supplied sessions are caller-owned; a created session is closed on failure
  and transferred on success. Creation/reset/action failures are handled in replay.
  deterministic is true/false/null; null means reset evidence is unavailable.
- `discover_actions` returns `(actions, blocked_reasons, input_fields)`. Its
  actions store native identities and separate ordinals per full locator match set.
  Each automatic interaction refreshes hierarchy and validates the live control.
- `crawl_baseline` returns/persists a discovery graph. Candidate replay uses
  its screen paths and checkpoint names, then returns capture/failure/reset counts.
- `compare_platform` returns scored result rows. `write_report` combines these
  with supplied coverage/provenance and returns the summary used for CLI status.
- JSON contracts are dictionaries rather than typed schemas. Make compatibility
  changes explicit, including behavior of older artifact/config files.

See [configuration](CONFIGURATION.md) and [artifact contracts](ARTIFACTS.md).

## Work safely on the baseline

Read REVIEW_FIXES.md for completed stabilization and current validation limits;
the assessment preserves the original triggers and results.
Add a focused regression test for each confirmed bug. Avoid rewriting working
market capability construction, explicit device targeting, BFS orchestration,
existing report escaping, or version/build matching without a concrete reason.

Comments describe current contracts and remaining limitations. Update them after
verified fixes; keep functional changes separate from explanatory-only edits.

## Testing and evidence

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_market_mode.py -v
.\.venv\Scripts\python.exe -m compileall -q osdiff.py osdiff tests
```

Use `./.venv/bin/python` for the same commands on POSIX. Install `requirements.txt`
first for execution/full tests. Help and prerequisite paths defer optional imports.
Current suite and CI evidence are in REVIEW_FIXES.md; the results below are historical.
The original attempt had 14 passing methods and three error entries, not a green
38-method suite. Compilation and isolated synthetic probes are separate evidence.

The tests use temporary artifacts/mocks and do not validate physical devices,
signing, real Appium transport, printer safety, or simulator runtime behavior.
Global Appium/Selenium stubs have been removed. CI runs every module independently
and verifies capability serialization using the real installed client. Scoped
driver/process mocks still do not validate live transport or devices.

The earlier documentation-only update verified unchanged executable ASTs in all 11 Python
files, added 135 top-level function contract docstrings, preserved runtime
configuration/scenario steps/dependency pins, parsed all four JSON data files,
checked local Markdown links, compiled Python, and parsed both PowerShell scripts.
The suite rerun still produced 14 passing methods and the same three error entries.
These checks establish an explanatory change, not fixes for the assessed defects.

For comment/docstring-only Python changes, compare parsed executable ASTs after
removing docstrings, then compile. For JSON examples, parse every file and confirm
runtime settings are unchanged. These checks complement the existing suite; they
do not establish full runtime safety. Record failures and unavailable tooling honestly.

## Review handoff

[PR #1](https://github.com/sairam7775/os-differential-regression-tester/pull/1)
is the completed Claude baseline audit against the pre-import branch. Its head
contains historical code, so merging that audit is not a rollout of these fixes.

[PR #2](https://github.com/sairam7775/os-differential-regression-tester/pull/2)
targets main with stabilization commits. [REVIEW_FIXES.md](REVIEW_FIXES.md) maps
findings to code/tests and documents deliberate safety compatibility changes.
Reviewers should inspect the exact current head and report severity, trigger,
impact, and regression evidence. Claude re-reviewed a85fb29; its four follow-ups
are mapped in REVIEW_FIXES.md. The resulting revision is not yet approved by Claude. A GitHub comment does not prove delivery to an already-running local session.

## Real-device acceptance after stabilization

Record the tested commit, tool/driver versions, authorized devices, matched app
version/build, verified OS/build difference, environment, and test-data setup.
Keep serials, credentials, hierarchy, and screenshots private. Verify launch,
capture, reset, navigation replay, report/exit-code consistency, and binary
preservation. No generic printing, pairing, firmware, purchase, or destructive
operations belong in automatic safe-mode acceptance. iOS needs macOS, two real
iPhones, valid WDA signing, and honest non-deterministic reset reporting unless
a verified external reset mechanism is available.
