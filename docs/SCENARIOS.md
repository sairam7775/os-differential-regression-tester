# Explicit scenario format

Scenario mode (`run`) uses virtual devices and operator-supplied APK/Simulator
`.app` binaries. It provides deterministic step intent, not automatic safe-mode
policy. Crawler deny rules do not apply to explicit scenarios. Review every
action and use dedicated test data; no destructive production/hardware operations.

## Root fields

| Field | Meaning |
| --- | --- |
| `name` | Scenario artifact directory and summary identity; use a unique simple name |
| `description` | Informational text; not used by the runner |
| `platforms` | Optional platform applicability, normally `android`/`ios` |
| `steps` | Ordered action/checkpoint dictionaries |

Names/checkpoint IDs become local paths; keep trusted identifiers without absolute
paths or `..`. Repeated names/IDs can overwrite artifact or summary identity.
The sample core_navigation IDs are placeholders, not INSTAX app identifiers.

## Steps and locators

| Type | Main fields | Behavior |
| --- | --- | --- |
| `tap` | `locator`, optional `timeout` | Wait for presence and click |
| `type_text` | `locator`, `text`, optional `clear`, `timeout` | Expand env variables and send keys; failed clearing is ignored |
| `wait_for` | `locator`, optional `timeout` | Wait for presence, not necessarily visibility |
| `sleep` | `seconds` | Fixed pause |
| `back` | none | Driver back action |
| `swipe` | `startX/startY/endX/endY`, `durationMs` | Window-relative coordinates |
| `terminate_app` | `appId` | Terminate specified app |
| `activate_app` | `appId` | Activate specified app |
| `checkpoint` | `id`, optional `assertions`, `settleSeconds` | Readiness assertions, settling, screenshot/hierarchy/state capture |

Non-checkpoint steps may set `platforms` and `continueOnFailure`. The latter
records a failed action and continues; current scenario status can still be
passed. Failure evidence after the last checkpoint requires summary validation.
`secure` is an example metadata hint on text entry; it does not enforce redaction.

Locator shapes are shared `{strategy, value}` or per-platform dictionaries:

```json
{"android": {"strategy": "accessibility_id", "value": "home_title"},
 "ios": {"strategy": "accessibility_id", "value": "home_title"}}
```

Strategies: `accessibility_id`, `id`, `xpath`, `class_name`,
`android_uiautomator`, `ios_predicate`, `ios_class_chain`. Prefer stable IDs.
Neither strategy validation nor sample locators establish that an intended
control exists on a real application; replace placeholders and test readiness.

## Assertions and capture

Assertions support `element_present`, `text_equals`, `enabled`, and `displayed`,
with `locator`, optional `timeout`, and `value` for comparisons. Text expectations
expand environment variables. Assertions return passed/message records rather
than raising; false assertions currently do not stop checkpoint capture.

```json
{"type": "checkpoint", "id": "home", "settleSeconds": 0.5,
 "assertions": [{"type": "element_present",
   "locator": {"strategy": "accessibility_id", "value": "home_title"}}]}
```

Assertions run before screenshots/source. Each checkpoint persists actions since
the previous checkpoint, window size, and capture epoch. Session startup/step
exceptions return failed scenario details and attempt quit. Baseline assertion
failures are not yet fully invalidated by the comparator; see the assessment.

## Credentials and OS-sensitive flows

Use `${TEST_USER_EMAIL}`/`${TEST_USER_PASSWORD}` environment references in trusted
scenario files; `.env` is not automatically loaded. Current assertions/errors and
raw hierarchy redaction have privacy gaps, so do not use personal credentials.
Set storage screenshot masks separately from comparison ignore masks.

Cover camera/photo/file picker, permissions, keyboards, accessibility, background/
foreground, offline recovery, and navigation with explicit checkpoints. OS-sensitive
system locators can differ; maintain meaningful assertions instead of weakening
validity. Real printer/firmware/payment flows require a separately reviewed hardware
test process and do not belong in automatic safe-mode crawling.
