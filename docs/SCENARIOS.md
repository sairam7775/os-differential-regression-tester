# Scenarios — v0.5 Context

Scenario mode remains available for controlled flows. For hardware companion applications, use explicit scenarios for print, firmware, reset, payment or other side-effecting operations rather than disabling crawler safety globally.

---

# Scenario format

Scenarios are JSON and are intentionally explicit.

## Actions

Supported:

- `tap`
- `type_text`
- `wait_for`
- `sleep`
- `back`
- `swipe`
- `terminate_app`
- `activate_app`
- `checkpoint`

## Locator strategies

Preferred order:

1. `accessibility_id`
2. native ID
3. iOS predicate / class chain or Android UIAutomator
4. XPath only when necessary

Stable accessibility IDs make the same scenario usable across OS versions.

## Checkpoints

A checkpoint captures:

- screenshot
- UI/accessibility hierarchy
- assertions
- actions since the prior checkpoint
- screen size

Example:

```json
{
  "type": "checkpoint",
  "id": "settings",
  "assertions": [
    {
      "type": "element_present",
      "locator": {
        "android": {"strategy": "accessibility_id", "value": "settings_title"},
        "ios": {"strategy": "accessibility_id", "value": "settings_title"}
      }
    }
  ]
}
```

## Assertions

Supported:

- `element_present`
- `text_equals`
- `enabled`
- `displayed`

## Recommended screen inventory

Cover both normal app screens and OS-sensitive integrations:

- cold launch / splash
- login / authentication
- home / navigation
- lists and details
- search
- create/edit
- settings/profile
- permissions
- camera
- photo picker
- file picker
- notifications
- deep links
- biometrics
- keyboard/input
- background → foreground
- offline → online recovery
- dark mode
- large text / accessibility
- logout
- upgrade/migration-sensitive flows

Do not put destructive production actions in automated scenarios.

## v0.2 permission testing guidance

Android permissions are not auto-granted by default. Treat permission prompts as explicit OS-sensitive scenarios where possible, especially:

- notifications
- photos/media
- camera
- microphone
- foreground/background location
- Bluetooth / nearby devices

A permission scenario should checkpoint the app state before requesting permission, perform the action that triggers the system prompt, then assert the post-decision app state. System prompt locators can differ across OS versions, so keep platform/version-specific steps isolated rather than weakening the normal app-screen assertions.

## Checkpoint readiness

Checkpoint assertions run before screenshot/UI hierarchy capture. Use assertions to prove the intended screen is ready. You can override stabilization per checkpoint:

```json
{
  "type": "checkpoint",
  "id": "home",
  "settleSeconds": 0.5,
  "assertions": [
    {
      "type": "element_present",
      "locator": {
        "android": {"strategy": "accessibility_id", "value": "home_screen"},
        "ios": {"strategy": "accessibility_id", "value": "home_screen"}
      }
    }
  ]
}
```
