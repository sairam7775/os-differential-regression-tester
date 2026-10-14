# Automated test scope and actual results

Install requirements.txt in the project virtual environment, then run:

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p test_market_mode.py -v
python -m unittest discover -s tests -p test_hardening.py -v
python -m unittest discover -s tests -p test_regressions.py -v
python -m unittest discover -s tests -p test_review_fixes.py -v
python -m unittest discover -s tests -p test_review_artifacts.py -v
```

Use `.\.venv\Scripts\python.exe` on Windows or `./.venv/bin/python` on POSIX.
There are 104 methods across five modules. Driver/process boundaries use scoped
mocks, temporary synthetic artifacts, and real Pillow fixtures. Installed
Appium/Selenium modules are never replaced by process-global stubs.

| Module | Methods | Main coverage |
| --- | --- | --- |
| test_market_mode.py | 15 | Exact build/origin/OS/model/environment gates, runtime and metadata |
| test_hardening.py | 15 | Blockers/traces/reset, timing, report validity, privacy, subprocess/locks |
| test_regressions.py | 8 | Empty checkpoints, failures, duplicate hierarchy, HTML/readiness/paths |
| test_review_fixes.py | 45 | Live control/descendant/ordinal safety, foreground, input/privacy, OS/post-run gates, both-device coverage, locks and process lifecycle |
| test_review_artifacts.py | 21 | Real image/JSON/XML invalidation, strict assertions/timing, scenario/privacy, logs and real SDK capabilities |

[CI at behavior commit b77baf1](https://github.com/sairam7775/os-differential-regression-tester/actions/runs/38554498609)
ran 104 tests per job on Windows/Linux Python 3.11/3.14: 103 passed, one platform
skip, zero failures/errors. CI also runs each module independently, compiles,
and checks CLI argument/help paths. Windows skips POSIX permissions; Linux skips
Windows process queries. Real capability tests execute with installed Appium.
Consult PR #2 checks for the final documentation head.

Restricted local Windows discovery loaded 63 entries: 60 passing methods, three
discovery errors because Pillow was unavailable. This is not a local full-suite
pass. The original import had 14 passes, one method error, and two discovery errors.
[BASELINE_ASSESSMENT.md](../docs/BASELINE_ASSESSMENT.md) preserves that history.

No real device, emulator, simulator, signing, live Appium, or printer tests occurred.
[REVIEW_FIXES.md](../docs/REVIEW_FIXES.md) maps comments to fixes and records
remaining limitations and justified compatibility changes.
