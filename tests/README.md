# Automated test scope and baseline results

Install `requirements.txt` in the tool-local virtual environment, then run:

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p test_market_mode.py -v
python -m unittest discover -s tests -p test_hardening.py -v
python -m unittest discover -s tests -p test_regressions.py -v
```

Use `.\.venv\Scripts\python.exe` on Windows or `./.venv/bin/python` on POSIX
to avoid selecting the wrong interpreter. There are 38 test methods across
three modules. Existing tests use synthetic hierarchy/images/JSON, temporary
directories, and fake/mocked drivers/processes; they do not operate real devices.

| Module | Main coverage |
| --- | --- |
| `test_market_mode.py` | Version/build/origin/OS/model/environment gates, preinstalled runtimes, metadata parsing |
| `test_hardening.py` | Deny precedence, truncation, fingerprints, missing ordinals, replay failures, reset, traces, XML/report validity, permissions, timeouts/lock helper |
| `test_regressions.py` | Empty checkpoints, baseline/candidate execution failure, duplicate hierarchy nodes, HTML escaping, readiness order, path resolution |

The original Windows/Python 3.14.7 attempt returned exit 1: 14 passing methods,
one test-method error, two module-discovery errors, and `Ran 17 tests`.
Pillow (`PIL`) was missing for two modules; the iOS metadata test's partial
Appium mock failed to supply options imports. Installation was attempted but
unavailable in this environment. This is not a passing full-suite baseline.

`test_hardening` installs global Appium/Selenium stubs if not already imported,
even when real clients are installed. Other modules can depend on that import
order. The optional runner test may run against stubbed classes; that is not
real-client capability serialization coverage. Replace process-global fakes
with scoped fixtures during stabilization and keep independent module runs.

Known gaps include safe duplicate-control resolution, Windows process-safe lock
ownership/cleanup, XML-preserving redaction, secret/ID leakage through all artifacts,
malformed summaries/states, failed baseline assertions, trailing/missing actions,
candidate reset/input evidence, positive OS identity, post-run build verification,
and session/capture/setup cleanup. Add focused regressions when fixing these,
without weakening market/safety/coverage invariants.

See [baseline assessment](../docs/BASELINE_ASSESSMENT.md) for actual evidence and
[developer guide](../docs/DEVELOPER_GUIDE.md) for compilation/AST/documentation
checks. Passing synthetic tests cannot establish real-device or printer safety.
