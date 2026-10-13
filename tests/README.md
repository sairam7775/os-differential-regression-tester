# Regression tests

Run from the tool root:

```bash
python -m unittest discover -s tests -v
```

The v0.5 suite covers:

- no-checkpoint / baseline false-PASS prevention;
- candidate execution failures;
- hierarchy duplicate handling and malformed hierarchy invalidation;
- HTML escaping and PARTIAL→INVALID report consistency;
- deny-rule precedence (`Continue to Pay/Print`);
- action truncation coverage blockers;
- text-sensitive screen fingerprinting;
- stale ordinal handling;
- baseline replay failure coverage;
- action-trace/timing regression comparison;
- Android deterministic app-data reset;
- unknown iOS foreground-app rejection;
- exact market version/build and OS-build identity rules;
- environment/model validation;
- iOS `listApps returnAttributes` contract;
- private artifact permissions;
- subprocess timeout handling;
- single-run lock;
- path resolution and checkpoint ordering.
