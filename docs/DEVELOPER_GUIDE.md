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
  and transferred on success. Creation itself is outside its replay exception handler.
- `discover_actions` returns `(actions, blocked_reasons, input_fields)`. Its
  locator/ordinal representation is known to need safe live-target validation.
- `crawl_baseline` returns/persists a discovery graph. Candidate replay uses
  its screen paths and checkpoint names, then returns capture/failure/reset counts.
- `compare_platform` returns scored result rows. `write_report` combines these
  with supplied coverage/provenance and returns the summary used for CLI status.
- JSON contracts are dictionaries rather than typed schemas. Make compatibility
  changes explicit, including behavior of older artifact/config files.

See [configuration](CONFIGURATION.md) and [artifact contracts](ARTIFACTS.md).

## Work safely on the baseline

Read the assessment before implementing fixes. Start with safe action resolution,
Windows lock lifecycle, redaction, then false-PASS/coverage/provenance validation.
Add a focused regression test for each confirmed bug. Avoid rewriting working
market capability construction, explicit device targeting, BFS orchestration,
existing report escaping, or version/build matching without a concrete reason.

Documentation currently marks unresolved defects directly in source docstrings.
Update those notes when a fix is implemented and verified; do not treat a comment
as a fix. Keep any functional fix in a separate logical commit from explanatory edits.

## Testing and evidence

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_market_mode.py -v
.\.venv\Scripts\python.exe -m compileall -q osdiff.py osdiff tests
```

Use `./.venv/bin/python` for the same commands on POSIX. Install `requirements.txt`
first; dependencies are not currently optional for all test/CLI paths.
The original attempt had 14 passing methods and three error entries, not a green
38-method suite. Compilation and isolated synthetic probes are separate evidence.

The tests use temporary artifacts/mocks and do not validate physical devices,
signing, real Appium transport, printer safety, or simulator runtime behavior.
Global Appium/Selenium stubs currently create import-order coupling; run modules
individually while stabilizing them. An imported fake options class does not
verify serialization by the real installed client.

The documentation update verified unchanged executable ASTs in all 11 Python
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
is a retrospective full-code review. Its base branch holds the pre-import commit;
its head holds the reviewed code/documentation. It does not target `main`, which
already contains the import. Merging it is not a rollout of fixes to `main`.

A separate local Claude read-only command was launched with the PR instructions.
No completed result has been received. Creating a GitHub PR alone does not deliver
input to an already-running Claude conversation. Reviewers should use the current
PR head and exact line references, independently verify assessment findings, and
return severity, trigger, impact, and proposed regression tests.

## Real-device acceptance after stabilization

Record the tested commit, tool/driver versions, authorized devices, matched app
version/build, verified OS/build difference, environment, and test-data setup.
Keep serials, credentials, hierarchy, and screenshots private. Verify launch,
capture, reset, navigation replay, report/exit-code consistency, and binary
preservation. No generic printing, pairing, firmware, purchase, or destructive
operations belong in automatic safe-mode acceptance. iOS needs macOS, two real
iPhones, valid WDA signing, and honest non-deterministic reset reporting unless
a verified external reset mechanism is available.
