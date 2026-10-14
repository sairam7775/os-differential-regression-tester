"""Discover baseline UI states and replay retained paths on a candidate.

Each branch starts with its configured reset. Actions retain native identities
and per-locator occurrences; live attributes and descendant safety are verified
before interaction. Both targets contribute reset, input, and coverage evidence.
See docs/AUTO_DISCOVERY.md for remaining graph and scrolling limitations."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
import unicodedata
from collections import deque
from pathlib import Path
from xml.etree import ElementTree as ET


from osdiff.fsutil import mask_image_regions, private_dir, private_file, redact_values, redact_xml, write_json, write_text
from osdiff.runner import _options

# Only narrowly recognized permission dialogs can be traversed outside the app.
DEFAULT_ANDROID_SYSTEM_PACKAGES = {
    "com.android.permissioncontroller", "com.google.android.permissioncontroller",
}
DEFAULT_IOS_SYSTEM_BUNDLES = {"com.apple.springboard"}
FORBIDDEN_SYSTEM_SURFACES = {
    "com.android.settings", "com.android.packageinstaller", "com.google.android.packageinstaller",
    "com.apple.Preferences",
}
MANDATORY_DENY_PATTERNS = [
    r"\b(?:un)?pair(?:ing|ed|s)?\b", r"\b(?:dis)?connect(?:ion|ions|ing|ed|s)?\b",
    r"\bbluetooth\b", r"\b(?:re)?print(?:ing|ed|s|er|ers)?\b", r"firmware",
    r"\b(?:pay(?:ment|ments|ing)?|purchas(?:e|es|ing)|buy|checkout|reorder)\b",
    r"^\s*order\s*$", r"\b(?:place|confirm|submit)\s+(?:(?:an?|the)\s+)?order\b|\border\s+(?:now|again)\b",
    r"\b(?:delet(?:e[ds]?|ing)|eras(?:e[ds]?|ing)|remov(?:e|es|ing)|updat(?:e|ing)|(?:un)?install(?:ed|ing|s)?|reset(?:s|ting)?|forget(?:s|ting)?)\b",
    r"\bclear\s+(?:data|storage|cache)\b", r"\bforce\s+stop\b",
    r"\b(?:send|submit)\b", r"\b(?:sign|log)\s*out\b",
    r"\b(?:usb\s+debugging|airplane\s+mode)\b",
]
PERMISSION_LABELS = {
    "allow", "don't allow", "dont allow", "deny", "not now", "cancel",
    "allow once", "allow while using app", "allow while using the app",
    "while using the app", "only this time", "ask app not to track",
}

def _safety_values(node):
    """Keep individual captions available for imperative checks on unnamed containers."""
    return [str(value) for child in node.iter() for key, value in child.attrib.items()
            if key in {"text", "content-desc", "name", "label", "resource-id", "class", "type"} and value]


def _caption_danger_reason(values, cfg):
    """Check each caption as well as joined metadata; allow rules never override denies."""
    return next((reason for value in [*values, " ".join(values)]
                 if (reason := _danger_reason(value, cfg))), None)


def _safety_text(node):
    """Include descendant captions in the identity of a clickable container."""
    return " ".join(_safety_values(node))

def _control_identity(node):
    """Stable native attributes and descendant captions, excluding geometry and input values."""
    return {"attributes": {k: v for k, v in node.attrib.items()
                           if k in {"class", "type", "resource-id", "content-desc", "text", "name", "label", "password"}},
            "captions": _safety_text(node)}

def _locator_matches(node, locator):
    attrs = node.attrib
    value = locator["value"]
    if locator["strategy"] == "id":
        return attrs.get("resource-id") == value
    if locator["strategy"] == "accessibility_id":
        return attrs.get("content-desc") == value or attrs.get("name") == value
    if locator["strategy"] == "class_name":
        return attrs.get("class") == value or attrs.get("type") == value
    # Generated XPath locators are equality predicates, not arbitrary caller XPath.
    return any(value == f"//*[@{key}={_xpath_literal(attrs[key])}]"
               for key in ("text", "label") if attrs.get(key))

def _identified_control(node, nodes, platform):
    locators = _locators(platform, node.attrib)
    for locator in locators:
        matches = [entry for entry in nodes if _locator_matches(entry, locator)]
        locator["ordinal"] = matches.index(node)
    return {"locators": locators, "ordinal": locators[0]["ordinal"] if locators else 0,
            "identity": _control_identity(node)}

def _permission_action(node, platform):
    if platform == "android":
        return bool(re.search(r":id/permission_(?:allow|deny)(?:_[a-z]+)*_button$", node.attrib.get("resource-id", "")))
    return _label(platform, node.attrib).lower().replace("\u2019", "'") in PERMISSION_LABELS

def _attribute(element, names):
    for name in names:
        try:
            value = element.get_attribute(name)
        except Exception:
            continue
        if value is not None:
            return str(value)
    return None

def _verify_live_control(element, identity, platform, cfg):
    """Check the selected live element's own attributes and descendant safety captions."""
    aliases = {"resource-id": ("resourceId", "resource-id"), "class": ("className", "class"),
               "content-desc": ("contentDescription", "content-desc")}
    expected = identity["attributes"]
    if (_attribute(element, ("enabled",)) or "").lower() != "true":
        raise RuntimeError("Live control is not enabled")
    for key, value in expected.items():
        if _attribute(element, aliases.get(key, (key,))) != str(value):
            raise RuntimeError("Live control identity changed before interaction")
    try:
        descendants = element.find_elements("xpath", ".//*")
    except Exception as exc:
        raise RuntimeError("Unable to verify descendant safety before interaction") from exc
    captions = []
    for child in [element, *descendants]:
        for name in ("text", "contentDescription", "content-desc", "name", "label", "resourceId"):
            value = _attribute(child, (name,))
            if value:
                captions.append(value)
    if cfg.get("safeMode", True) and _caption_danger_reason(captions, cfg):
        raise RuntimeError("Live control blocked by safety policy")

def _current_control(driver, platform, action, cfg):
    """Resolve recorded identity against a fresh hierarchy before querying live locators."""
    if not action.get("identity"):
        raise RuntimeError("Automatic action lacks a verified control identity")
    context = cfg.get("_foregroundContext")
    actions, _, _ = discover_actions(driver.page_source or "", platform, cfg, context=context)
    matches = [entry for entry in actions if entry.get("identity") == action["identity"]
               and entry.get("ordinal") == action.get("ordinal") and entry.get("kind") == action.get("kind")]
    if len(matches) != 1:
        raise RuntimeError("Recorded control is missing, ambiguous, or blocked")
    element = _find_for_action(driver, matches[0])
    if element is None:
        raise RuntimeError("Expected control occurrence not found")
    _verify_live_control(element, matches[0]["identity"], platform, cfg)
    return element

def _merge_reset(left, right):
    if left is False or right is False:
        return False
    if left is None or right is None:
        return None
    return True

def _reset_status(evidence):
    return "UNKNOWN" if evidence is None else ("DETERMINISTIC" if evidence else "NON_DETERMINISTIC")


def _truthy(value):
    """Normalize selected XML string booleans from Android/iOS hierarchy attributes."""
    return str(value).lower() in {"1", "true", "yes"}


def _xml_root(source):
    """Parse native hierarchy XML, returning None so discovery can record a parse blocker."""
    try:
        return ET.fromstring(source)
    except Exception:
        return None


def _xpath_literal(value):
    """Encode text as an XPath literal, including values containing both quote styles."""
    value = str(value)
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    pieces = value.split('"')
    return "concat(" + ', \'"\', '.join(f'"{p}"' for p in pieces) + ")"


def _bounds_android(value):
    """Parse positive Android bounds [x1,y1][x2,y2]; invalid/zero-sized bounds return None."""
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", value or "")
    if not match:
        return None
    x1, y1, x2, y2 = map(int, match.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}


def _bounds_ios(attrs):
    """Convert iOS position/dimensions to an integer rectangle, or return None."""
    try:
        x, y = int(float(attrs.get("x", 0))), int(float(attrs.get("y", 0)))
        w, h = int(float(attrs.get("width", 0))), int(float(attrs.get("height", 0)))
        if w <= 0 or h <= 0:
            return None
        return {"x": x, "y": y, "width": w, "height": h}
    except Exception:
        return None


def _label(platform, attrs):
    """Choose the first non-empty descriptive hierarchy attribute, not a merged control identity."""
    if platform == "android":
        values = [attrs.get("content-desc"), attrs.get("text"), attrs.get("resource-id"), attrs.get("class")]
    else:
        values = [attrs.get("name"), attrs.get("label"), attrs.get("value"), attrs.get("type")]
    return next((str(v).strip() for v in values if str(v or "").strip()), "")


def _is_input(platform, attrs):
    """Recognize native text fields; custom/web controls are outside this heuristic."""
    if platform == "android":
        return "EditText" in attrs.get("class", "") or _truthy(attrs.get("editable"))
    return attrs.get("type") in {"XCUIElementTypeTextField", "XCUIElementTypeSecureTextField"}


def _is_scrollable(platform, attrs):
    """Recognize native scroll containers; discovery currently queues only a window-wide down swipe."""
    if platform == "android":
        return _truthy(attrs.get("scrollable"))
    return attrs.get("type", "") in {
        "XCUIElementTypeScrollView", "XCUIElementTypeCollectionView",
        "XCUIElementTypeTable", "XCUIElementTypeWebView",
    }


def _is_actionable(platform, attrs):
    """Filter native controls by enabled/visible/type heuristics; this does not prove tap safety."""
    if str(attrs.get("enabled", "true")).lower() == "false":
        return False
    if platform == "android":
        return _truthy(attrs.get("clickable"))
    if str(attrs.get("visible", "true")).lower() == "false":
        return False
    return attrs.get("type", "") in {
        "XCUIElementTypeButton", "XCUIElementTypeCell", "XCUIElementTypeLink",
        "XCUIElementTypeTab", "XCUIElementTypeSwitch", "XCUIElementTypeImage",
        "XCUIElementTypeStaticText",
    }


def _locators(platform, attrs):
    """Return ordered ID/accessibility/text/class locator candidates for later replay."""
    locators = []
    if platform == "android":
        rid, desc, text, cls = (
            attrs.get("resource-id"), attrs.get("content-desc"), attrs.get("text"), attrs.get("class")
        )
        if rid:
            locators.append({"strategy": "id", "value": rid})
        if desc:
            locators.append({"strategy": "accessibility_id", "value": desc})
        if text:
            locators.append({"strategy": "xpath", "value": f"//*[@text={_xpath_literal(text)}]"})
        if cls:
            locators.append({"strategy": "class_name", "value": cls})
    else:
        name, label, typ = attrs.get("name"), attrs.get("label"), attrs.get("type")
        if name:
            locators.append({"strategy": "accessibility_id", "value": name})
        if label and label != name:
            locators.append({"strategy": "xpath", "value": f"//*[@label={_xpath_literal(label)}]"})
        if typ:
            locators.append({"strategy": "class_name", "value": typ})
    return locators


def _danger_reason(text, cfg):
    """Deny mandatory hardware/destructive actions plus operator-configured patterns."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).replace("_", " ").replace("-", " ")
    for deny in [*MANDATORY_DENY_PATTERNS, *cfg.get("denyKeywords", [])]:
        if re.search(deny, text, re.I):
            return f"blocked_by_keyword:{deny}"
    return None


def _normalize_for_fingerprint(source, cfg):
    """Serialize configured hierarchy attributes in tree order with dynamic-value normalization."""
    root = _xml_root(source)
    if root is None:
        return re.sub(r"\s+", " ", source or "").strip()

    attributes = cfg.get(
        "fingerprintAttributes",
        ["type", "class", "name", "label", "text", "value", "resource-id", "content-desc", "enabled", "clickable", "scrollable"],
    )
    ignore_patterns = [re.compile(p) for p in cfg.get("fingerprintIgnorePatterns", [])]
    rows = []

    def normalized(value):
        value = str(value)
        for pattern in ignore_patterns:
            value = pattern.sub("<dynamic>", value)
        return value

    def walk(node, depth=0):
        values = []
        for key in attributes:
            value = node.attrib.get(key)
            if value not in (None, ""):
                values.append(f"{key}={normalized(value)}")
        if values:
            rows.append(f"{depth}:{node.tag}:" + "|".join(values))
        for child in list(node):
            walk(child, depth + 1)

    walk(root)
    return "\n".join(rows)


def state_fingerprint(source, cfg, context=None):
    """Hash normalized hierarchy and stable package/activity/bundle context.
    
    Transient process IDs are excluded. This identifies discovery states rather than
    proving that a candidate destination is semantically equivalent."""
    normalized = _normalize_for_fingerprint(source, cfg)
    context = {k: v for k, v in (context or {}).items() if k in {"package", "activity", "bundleId"}}
    if context:
        normalized += "\n@context:" + "|".join(f"{k}={context[k]}" for k in sorted(context) if context[k])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def discover_actions(source, platform, cfg, context=None):
    """Discover identified controls; count locator occurrences before any filtering."""
    root = _xml_root(source)
    if root is None:
        return [], [{"label": "(hierarchy)", "reason": "hierarchy_parse_failed"}], []
    nodes = list(root.iter())
    actions, blocked, input_nodes = [], [], []
    has_scrollable = False
    system = bool(context and context.get("systemSurface"))
    for node in nodes:
        attrs = node.attrib
        bounds = _bounds_android(attrs.get("bounds")) if platform == "android" else _bounds_ios(attrs)
        if _is_input(platform, attrs) and not system:
            input_nodes.append({"label": _label(platform, attrs), "bounds": bounds,
                "secure": _truthy(attrs.get("password")) if platform == "android" else attrs.get("type") == "XCUIElementTypeSecureTextField",
                **_identified_control(node, nodes, platform)})
        if _is_scrollable(platform, attrs) and not system:
            has_scrollable = True
        if not _is_actionable(platform, attrs) or not bounds:
            continue
        label = _label(platform, attrs)
        if system and not _permission_action(node, platform):
            continue
        reason = _caption_danger_reason(_safety_values(node), cfg)
        if cfg.get("safeMode", True) and reason:
            blocked.append({"label": label or "(unnamed)", "reason": reason})
            continue
        identified = _identified_control(node, nodes, platform)
        if not identified["locators"]:
            blocked.append({"label": label or "(unidentified control)", "reason": "no_stable_locator"})
            continue
        actions.append({"kind": "tap", "label": label or "(unnamed)", "bounds": bounds, **identified})
    if has_scrollable and cfg.get("enableScrolling", True):
        actions.append({"kind": "scroll_down", "label": "Scroll down"})
    if system and not actions:
        blocked.append({"label": "(system surface)", "reason": "no_recognized_permission_action"})
    actions.sort(key=lambda a: (a["kind"] == "scroll_down",
        0 if any(l["strategy"] in ("id", "accessibility_id") for l in a.get("locators", [])) else 1, a["label"]))
    limit = int(cfg.get("maxActionsPerScreen", 24))
    if limit <= 0:
        raise ValueError("maxActionsPerScreen must be positive")
    if len(actions) > limit:
        blocked.append({"label": "(action limit)", "reason": "actions_truncated", "totalActions": len(actions), "exploredActions": limit})
    return actions[:limit], blocked, input_nodes


def _find_elements(driver, locator):
    """Query a locator and collapse exceptions to no matches; transport errors lose their cause."""
    from appium.webdriver.common.appiumby import AppiumBy
    mapping = {
        "id": AppiumBy.ID, "accessibility_id": AppiumBy.ACCESSIBILITY_ID,
        "xpath": AppiumBy.XPATH, "class_name": AppiumBy.CLASS_NAME,
    }
    by = mapping.get(locator["strategy"])
    if by is None:
        return []
    try:
        return driver.find_elements(by, locator["value"])
    except Exception:
        return []


def _find_for_action(driver, action):
    """Try locators using each locator's occurrence in its full native match set.
    
    Filtering never renumbers occurrences. A returned element still needs fresh
    identity and safety validation before interaction."""
    for locator in action.get("locators", []):
        ordinal = int(locator.get("ordinal", action.get("ordinal", 0)))
        if ordinal < 0:
            continue
        matches = _find_elements(driver, locator)
        if ordinal < len(matches):
            return matches[ordinal]
    return None


def _tap(driver, platform, action, cfg=None):
    """Click a freshly identified, safety-checked live control exactly once.

    No coordinate or gesture retry follows an uncertain click outcome in safe mode.
    """
    cfg = cfg or {}
    element = _current_control(driver, platform, action, cfg)
    element.click()


def _scroll(driver, platform):
    """Swipe downward through the visible window; no container or scroll-end evidence is returned."""
    size = driver.get_window_size()
    x = int(size["width"] * 0.5)
    driver.swipe(x, int(size["height"] * 0.78), x, int(size["height"] * 0.25), 450)


def execute_action(driver, platform, action, settle_seconds=0.5, cfg=None):
    """Execute a tap/down-scroll and sleep for stabilization; foreground checking belongs to replay."""
    if action["kind"] == "tap":
        _tap(driver, platform, action, cfg)
    elif action["kind"] == "scroll_down":
        _scroll(driver, platform)
    else:
        raise RuntimeError(f"Unsupported crawler action: {action['kind']}")
    time.sleep(settle_seconds)


def _input_value(rule):
    """Resolve an input rule from its environment variable, falling back to an inline value."""
    if rule.get("env"):
        value = os.getenv(rule["env"])
        if value is not None:
            return value
    return rule.get("value")


def _input_id(field):
    """Identify a replay prerequisite by a stable locator and its native occurrence."""
    locators = field.get("locators", [])
    locator = next((item for strategy in ("id", "accessibility_id", "class_name")
                    for item in locators if item["strategy"] == strategy), None)
    if locator is None:
        return None
    return {"strategy": locator["strategy"], "value": locator["value"],
            "ordinal": locator.get("ordinal", field.get("ordinal", 0))}


def fill_known_inputs(driver, platform, source, cfg):
    """Fill rules only after native identity/security checks; block uncertain fields."""
    _, _, inputs = discover_actions(source, platform, cfg)
    filled, blocked = [], []
    for field in inputs:
        label = field["label"]
        rule = next((r for r in cfg.get("autoInputRules", []) if re.search(r.get("pattern", "$^"), label, re.I)), None)
        reason = None
        secret = bool(field["secure"])
        if not rule:
            reason = "no_auto_input_rule"
        else:
            secret = bool(secret or rule.get("secret") or rule.get("secure") or re.search(r"password|passcode|pin|token|secret", rule.get("env", ""), re.I))
            if secret and not field["secure"]:
                reason = "secret_requires_secure_field"
            value = _input_value(rule) if reason is None else None
            if reason is None and value in (None, ""):
                reason = f"missing_input_value:{rule.get('env', 'inline')}"
        if reason:
            blocked.append({"label": label or "(input)", "reason": reason, "inputId": _input_id(field), "requiredForReplay": secret})
            continue
        element = _find_for_action(driver, field)
        if element is None:
            blocked.append({"label": label, "reason": "input_not_found", "inputId": _input_id(field), "requiredForReplay": secret})
            continue
        try:
            _verify_live_control(element, field["identity"], platform, cfg)
            live_secure = _truthy(_attribute(element, ("password",))) if platform == "android" else _attribute(element, ("type",)) == "XCUIElementTypeSecureTextField"
            if secret and not live_secure:
                raise RuntimeError("Secret requires a secure live field")
            element.clear()
            element.send_keys(str(value))
            filled.append({"label": label, "source": rule.get("env", "inline"), "inputId": _input_id(field)})
        except Exception as exc:
            blocked.append({"label": label, "reason": f"input_failed:{type(exc).__name__}", "inputId": _input_id(field), "requiredForReplay": secret})
    return filled, blocked


def _sensitive_values(cfg):
    """Collect configured secrets and environment-backed input values for literal redaction."""
    values = list(cfg.get("sensitiveValues", [])) + list(cfg.get("sensitiveDeviceIds", []))
    for rule in cfg.get("autoInputRules", []):
        if rule.get("value"):
            values.append(str(rule["value"]))
        env_name = rule.get("env")
        if env_name and os.getenv(env_name):
            values.append(os.getenv(env_name))
    return [v for v in values if v]


def _redact_source(source, cfg):
    """Redact decoded XML values and serialize without repairing malformed captures."""
    return redact_xml(source, _sensitive_values(cfg))


def _save_checkpoint(driver, platform, checkpoint, state_id, path_actions, out_root, cfg, metadata=None, recent_actions=None):
    """Capture a verified screenshot and sanitized hierarchy/state evidence.
    
    Storage masks run before report copies. A failed or missing screenshot raises;
    known input values and target identifiers are removed from XML and JSON strings."""
    folder = private_dir(Path(out_root) / "auto_crawl" / checkpoint)
    screenshot = folder / "screen.png"
    if driver.save_screenshot(str(screenshot)) is False or not screenshot.is_file():
        raise RuntimeError("Screenshot capture failed")
    mask_image_regions(screenshot, cfg.get("sensitiveRegions", {}).get(platform, []))
    private_file(screenshot)
    source = driver.page_source or ""
    write_text(folder / "source.xml", _redact_source(source, cfg))
    state = {
        "scenario": "auto_crawl", "checkpoint": checkpoint, "platform": platform,
        "crawler": True, "stateFingerprint": state_id, "path": path_actions,
        "assertions": [], "recentActions": recent_actions or [],
        "windowSize": driver.get_window_size(), "capturedEpoch": time.time(),
        "metadata": metadata or {},
    }
    write_json(folder / "state.json", state, sensitive_values=_sensitive_values(cfg))
    return source


def _new_driver(server_url, runtime, platform):
    """Create a target-specific Appium session using runner's shared capability construction."""
    from appium import webdriver
    return webdriver.Remote(server_url, options=_options(runtime, platform))


def _foreground_context(driver, platform):
    """Read Android package/activity or iOS bundle/pid, returning unknown fields on probe failure."""
    if platform == "android":
        package = None
        activity = None
        try:
            package = driver.current_package
        except Exception:
            pass
        try:
            activity = driver.current_activity
        except Exception:
            pass
        return {"package": package, "activity": activity}
    try:
        info = driver.execute_script("mobile: activeAppInfo", {}) or {}
    except Exception:
        info = {}
    return {"bundleId": info.get("bundleId"), "pid": info.get("pid")}


def _assert_allowed_foreground(driver, platform, runtime, cfg, *, after_activation=False):
    """Allow the target or a positively recognized transient permission dialog only."""
    context = _foreground_context(driver, platform)
    expected = runtime.get("appPackage") if platform == "android" else runtime.get("bundleId")
    current = context.get("package") if platform == "android" else context.get("bundleId")
    if not current:
        raise RuntimeError("Unable to determine the foreground application")
    if current == expected:
        return context
    allowed = DEFAULT_ANDROID_SYSTEM_PACKAGES if platform == "android" else DEFAULT_IOS_SYSTEM_BUNDLES
    if current in FORBIDDEN_SYSTEM_SURFACES or current not in allowed:
        raise RuntimeError("Navigation left the target app; external/system traversal blocked")
    root = _xml_root(driver.page_source or "")
    if root is None:
        raise RuntimeError("Unable to verify permission dialog hierarchy")
    if platform == "ios" and not any(n.attrib.get("type") == "XCUIElementTypeAlert" for n in root.iter()):
        raise RuntimeError("SpringBoard is not a verified permission alert")
    if not any(_permission_action(node, platform) for node in root.iter()):
        raise RuntimeError("System surface has no recognized permission control")
    context["systemSurface"] = True
    return context


def _run_reset_command(command, runtime, timeout):
    """Expand udid/appId placeholders and run an operator-owned argument array without a shell.
    
    A zero exit code is trusted as reset evidence; app/binary preservation is an
    operator contract, not independently verified by this helper."""
    if not isinstance(command, list) or not command:
        raise RuntimeError("resetCommand must be a non-empty JSON array")
    mapping = {
        "udid": runtime.get("udid", ""),
        "appId": runtime.get("appPackage") or runtime.get("bundleId") or "",
    }
    expanded = [str(part).format(**mapping) for part in command]
    subprocess.run(expanded, check=True, text=True, capture_output=True, timeout=timeout)


def _prepare_path(driver, runtime, platform, cfg):
    """Terminate, reset according to strategy, activate, and verify foreground; return reset determinism.
    
    Android pm clear preserves the binary but clears data/permissions. Simulator
    reinstallation belongs only to virtual testing. Real iOS relaunch returns False.
    Reset commands are trusted; explicit mode authorization is still incomplete."""
    app_id = runtime.get("appPackage") if platform == "android" else runtime.get("bundleId")
    if not app_id:
        # Virtual auto-run may let Appium infer the identity from the APK/.app.
        context = _foreground_context(driver, platform)
        app_id = context.get("package") if platform == "android" else context.get("bundleId")
        if app_id:
            if platform == "android":
                runtime["appPackage"] = app_id
                runtime.setdefault("appActivity", context.get("activity"))
            else:
                runtime["bundleId"] = app_id
    if not app_id:
        raise RuntimeError("Unable to determine target app package/bundle ID for automatic crawling")
    try:
        driver.terminate_app(app_id)
    except Exception:
        pass

    strategy = runtime.get("resetStrategy") or cfg.get("resetStrategy") or "relaunch"
    timeout = int(cfg.get("resetTimeoutSeconds", 45))
    deterministic = False
    if strategy == "android_clear_data":
        if platform != "android":
            raise RuntimeError("android_clear_data reset strategy is Android-only")
        adb = runtime.get("adbPath") or shutil.which("adb")
        if not adb:
            raise RuntimeError("adb is required for android_clear_data reset strategy")
        proc = subprocess.run(
            [adb, "-s", runtime["udid"], "shell", "pm", "clear", app_id],
            text=True, capture_output=True, timeout=timeout,
        )
        if proc.returncode != 0 or "Success" not in (proc.stdout or ""):
            raise RuntimeError(f"Unable to clear target app data: {(proc.stderr or proc.stdout).strip()}")
        deterministic = True
    elif strategy == "ios_simulator_reinstall":
        if platform != "ios" or runtime.get("preinstalled") or not runtime.get("appPath"):
            raise RuntimeError("ios_simulator_reinstall requires iOS and appPath")
        xcrun = shutil.which("xcrun")
        if not xcrun:
            raise RuntimeError("xcrun is required for iOS simulator reset")
        subprocess.run([xcrun, "simctl", "uninstall", runtime["udid"], app_id], text=True, capture_output=True, timeout=timeout)
        proc = subprocess.run([xcrun, "simctl", "install", runtime["udid"], runtime["appPath"]], text=True, capture_output=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"Unable to reinstall simulator app: {(proc.stderr or proc.stdout).strip()}")
        deterministic = True
    elif strategy == "reset_command":
        _run_reset_command(runtime.get("resetCommand"), runtime, timeout)
        deterministic = True
    elif strategy == "relaunch":
        deterministic = False
    elif strategy == "driver":
        # Intended for fresh emulator/simulator sessions. Within a reused session it is
        # not guaranteed to reset application data, so do not claim deterministic isolation.
        deterministic = False
    else:
        raise RuntimeError(f"Unsupported resetStrategy: {strategy}")

    try:
        activated = driver.activate_app(app_id)
        if activated is False:
            raise RuntimeError("activate_app returned false")
    except Exception as exc:
        raise RuntimeError(f"Unable to activate target app {app_id}: {exc}") from exc
    time.sleep(float(cfg.get("settleSeconds", 0.6)))
    _assert_allowed_foreground(driver, platform, runtime, cfg, after_activation=True)
    return deterministic


def replay_path(server_url, runtime, platform, path_actions, cfg, driver=None):
    """Replay with caller-owned sessions; preserve actual reset evidence even on action failure."""
    owns_driver = driver is None
    trace, deterministic = [], None
    cfg = dict(cfg, sensitiveDeviceIds=[*cfg.get("sensitiveDeviceIds", []), runtime.get("udid")])
    try:
        if driver is None:
            driver = _new_driver(server_url, runtime, platform)
        deterministic = _prepare_path(driver, runtime, platform, cfg)
        _assert_allowed_foreground(driver, platform, runtime, cfg)
        settle = float(cfg.get("settleSeconds", 0.6))
        for index, action in enumerate(path_actions):
            context = _assert_allowed_foreground(driver, platform, runtime, cfg)
            filled, blocked = ([], []) if context.get("systemSurface") else fill_known_inputs(driver, platform, driver.page_source or "", cfg)
            rec = {"index": index, "action": action, "status": "running", "durationSeconds": 0.0,
                   "inputsFilled": filled, "blockedInputs": blocked}
            start = time.perf_counter()
            try:
                filled_ids = [item["inputId"] for item in filled if item.get("inputId")]
                missing = [item for item in action.get("requiredInputs", []) if item not in filled_ids]
                rec["missingRequiredInputs"] = missing
                # Optional unruled fields remain empty and recorded; they do not stop navigation.
                if missing or any(item.get("requiredForReplay") for item in blocked):
                    raise RuntimeError("Replay input prerequisites are incomplete")
                execute_action(driver, platform, action, settle, dict(cfg, _foregroundContext=context))
                _assert_allowed_foreground(driver, platform, runtime, cfg)
                rec["status"] = "passed"
            except Exception as exc:
                rec.update(status="failed", error=redact_values(f"{type(exc).__name__}: {exc}", _sensitive_values(cfg)))
                raise
            finally:
                rec["durationSeconds"] = round(time.perf_counter() - start, 3)
                trace.append(rec)
        return driver, trace, None, deterministic
    except Exception as exc:
        if owns_driver:
            _close_driver(driver)
        return None, trace, redact_values(f"{type(exc).__name__}: {exc}", _sensitive_values(cfg)), deterministic


def _close_driver(driver):
    """Best-effort Appium quit; callers own deciding when a failed session must be replaced."""
    if driver:
        try:
            driver.quit()
        except Exception:
            pass


def crawl_baseline(server_url, runtime, platform, out_root, cfg):
    """Explore reset-based BFS paths and retain one checkpoint per normalized state.
    
    Creation/replay/capture failures are recorded as incomplete coverage. The graph
    still stores queued source edges without reliable resolved destination IDs."""
    cfg = dict(cfg, sensitiveDeviceIds=[*cfg.get("sensitiveDeviceIds", []), runtime.get("udid")])
    max_screens = int(cfg.get("maxScreens", 120))
    max_depth = int(cfg.get("maxDepth", 12))
    max_total_paths = int(cfg.get("maxTotalPaths", 800))
    settle = float(cfg.get("settleSeconds", 0.6))

    queue = deque([[]])
    visited = {}
    graph = {
        "platform": platform, "mode": "auto_crawl", "screens": [], "edges": [],
        "blockedActions": [], "blockedInputs": [], "replayFailures": [],
        "limits": {"maxScreens": max_screens, "maxDepth": max_depth, "maxTotalPaths": max_total_paths},
        "limitReached": False, "depthFrontierReached": False,
        "actionsTruncated": 0, "deterministicReset": True,
    }

    attempted_paths = 0
    driver = None
    try:
        while queue and len(visited) < max_screens and attempted_paths < max_total_paths:
            path_actions = queue.popleft()
            attempted_paths += 1
            used_driver, trace, replay_error, deterministic = replay_path(
                server_url, runtime, platform, path_actions, cfg, driver=driver
            )
            graph["deterministicReset"] = _merge_reset(graph["deterministicReset"], deterministic)
            graph["blockedInputs"].extend({"pathIndex": rec["index"], **item}
                for rec in trace for item in rec.get("blockedInputs", []))
            if used_driver is None:
                graph["replayFailures"].append({"path": path_actions, "error": replay_error, "trace": trace})
                _close_driver(driver)
                driver = None
                continue
            driver = used_driver
            state_id = None
            try:
                time.sleep(settle)
                source = driver.page_source or ""
                context = _assert_allowed_foreground(driver, platform, runtime, cfg)
                filled, blocked_inputs = ([], []) if context.get("systemSurface") else fill_known_inputs(driver, platform, source, cfg)
                if filled:
                    time.sleep(float(cfg.get("afterInputSettleSeconds", 0.3)))
                    source = driver.page_source or ""
                    context = _assert_allowed_foreground(driver, platform, runtime, cfg)
                state_id = state_fingerprint(source, cfg, context)
                if state_id in visited:
                    graph["blockedInputs"].extend({"checkpoint": visited[state_id], **item} for item in blocked_inputs)
                    continue
                checkpoint = f"screen_{len(visited)+1:04d}_{state_id[:8]}"
                visited[state_id] = checkpoint
                actions, blocked, _ = discover_actions(source, platform, cfg, context=context)
                graph["actionsTruncated"] += sum(1 for item in blocked if item.get("reason") == "actions_truncated")
                try:
                    _save_checkpoint(
                        driver, platform, checkpoint, state_id, path_actions, out_root, cfg,
                        metadata={
                            "depth": len(path_actions), "actionsDiscovered": len(actions),
                            "inputsFilled": filled, "blockedInputs": blocked_inputs,
                            "foreground": context,
                        },
                        recent_actions=trace,
                    )
                except Exception as exc:
                    graph["replayFailures"].append({"path": path_actions, "error": redact_values(f"capture_failed:{type(exc).__name__}", _sensitive_values(cfg)), "trace": trace})
                    visited.pop(state_id, None)
                    continue
                graph["screens"].append({
                    "checkpoint": checkpoint, "stateFingerprint": state_id, "depth": len(path_actions),
                    "path": path_actions, "actionsDiscovered": len(actions),
                    "actionLabels": [a.get("label") for a in actions],
                })
                graph["blockedActions"].extend({"checkpoint": checkpoint, **item} for item in blocked)
                graph["blockedInputs"].extend({"checkpoint": checkpoint, **item} for item in blocked_inputs)
    
                if len(path_actions) >= max_depth:
                    if actions:
                        graph["depthFrontierReached"] = True
                    continue
                for action in actions:
                    required_inputs = [item["inputId"] for item in filled if item.get("inputId")]
                    action = dict(action, requiredInputs=required_inputs)
                    child_path = path_actions + [action]
                    queue.append(child_path)
                    graph["edges"].append({"from": checkpoint, "action": action, "depth": len(child_path)})
            except Exception as exc:
                graph["replayFailures"].append({"path": path_actions, "error": redact_values(f"capture_or_state_failed:{type(exc).__name__}", _sensitive_values(cfg)), "trace": trace})
                if state_id is not None:
                    visited.pop(state_id, None)
                _close_driver(driver)
                driver = None
    finally:
        _close_driver(driver)

    if queue or len(visited) >= max_screens or attempted_paths >= max_total_paths:
        graph["limitReached"] = True
    graph["attemptedPaths"] = attempted_paths
    graph["discoveredScreens"] = len(visited)
    graph["queueRemaining"] = len(queue)
    graph["baselineReplayFailures"] = len(graph["replayFailures"])
    incomplete = any([
        graph["limitReached"], graph["depthFrontierReached"], graph["blockedInputs"],
        graph["blockedActions"], graph["replayFailures"],
        (not graph["deterministicReset"] and attempted_paths > 1),
    ])
    graph["coverageStatus"] = "PARTIAL" if incomplete else "COMPLETE_WITHIN_POLICY"
    graph["resetIsolationStatus"] = _reset_status(graph["deterministicReset"])
    graph["coverageNote"] = (
        "Coverage means all UI states reachable from launch under the current crawler policy, credentials/test data, "
        "reset strategy and configured limits. Replay failures, blocked/truncated actions, missing inputs, or a non-"
        "deterministic reset strategy force PARTIAL coverage."
    )

    out_root = private_dir(out_root)
    write_json(out_root / "auto-crawl-graph.json", graph, sensitive_values=_sensitive_values(cfg))
    summary = [{
        "scenario": "auto_crawl", "platform": platform,
        "status": "passed" if graph["discoveredScreens"] > 0 else "failed",
        "error": None if graph["discoveredScreens"] > 0 else "No screens discovered",
        "actions": [],
        "crawler": {
            "discoveredScreens": graph["discoveredScreens"], "coverageStatus": graph["coverageStatus"],
            "baselineReplayFailures": graph["baselineReplayFailures"], "resetIsolationStatus": graph["resetIsolationStatus"],
        },
    }]
    write_json(out_root / "run-summary.json", summary, sensitive_values=_sensitive_values(cfg))
    return graph


def replay_candidate_graph(server_url, runtime, platform, baseline_graph, out_root, cfg):
    """Replay baseline paths and capture candidate artifacts under baseline names.
    
    Reproduced counts captures, not confirmed destination equivalence. Failures and
    blocked inputs are retained; coverage combines reset evidence from both devices."""
    cfg = dict(cfg, sensitiveDeviceIds=[*cfg.get("sensitiveDeviceIds", []), runtime.get("udid")])
    reproduced, failures = 0, []
    blocked_all = []
    driver = None
    deterministic_all = True
    try:
        for screen in baseline_graph.get("screens", []):
            checkpoint = screen["checkpoint"]
            path_actions = screen.get("path", [])
            used_driver, trace, error, deterministic = replay_path(
                server_url, runtime, platform, path_actions, cfg, driver=driver
            )
            deterministic_all = _merge_reset(deterministic_all, deterministic)
            if used_driver is None:
                failures.append({"checkpoint": checkpoint, "error": error, "path": path_actions, "trace": trace})
                _close_driver(driver)
                driver = None
                continue
            driver = used_driver
            state_id = None
            try:
                time.sleep(float(cfg.get("settleSeconds", 0.6)))
                source = driver.page_source or ""
                context = _assert_allowed_foreground(driver, platform, runtime, cfg)
                filled, blocked_inputs = ([], []) if context.get("systemSurface") else fill_known_inputs(driver, platform, source, cfg)
                if filled:
                    time.sleep(float(cfg.get("afterInputSettleSeconds", 0.3)))
                    source = driver.page_source or ""
                blocked_all.extend({"checkpoint": checkpoint, **item} for item in blocked_inputs)
                context = _assert_allowed_foreground(driver, platform, runtime, cfg)
                state_id = state_fingerprint(source, cfg, context)
                try:
                    _save_checkpoint(
                        driver, platform, checkpoint, state_id, path_actions, out_root, cfg,
                        metadata={
                            "replayedFromBaseline": True,
                            "baselineStateFingerprint": screen.get("stateFingerprint"),
                            "inputsFilled": filled, "blockedInputs": blocked_inputs,
                            "foreground": context,
                        },
                        recent_actions=trace,
                    )
                except Exception as exc:
                    failures.append({"checkpoint": checkpoint, "path": path_actions, "error": f"capture_failed:{type(exc).__name__}", "trace": trace, "artifactInvalid": True})
                    continue
                blocked_all.extend({"checkpoint": checkpoint, "pathIndex": rec["index"], **item}
                    for rec in trace for item in rec.get("blockedInputs", []))
                reproduced += 1
            except Exception as exc:
                failures.append({"checkpoint": checkpoint, "path": path_actions, "error": f"capture_or_state_failed:{type(exc).__name__}", "trace": trace, "artifactInvalid": True})
                _close_driver(driver)
                driver = None
    finally:
        _close_driver(driver)

    result = {
        "platform": platform, "mode": "candidate_replay",
        "baselineScreens": len(baseline_graph.get("screens", [])),
        "reproducedScreens": reproduced, "failedPaths": failures,
        "deterministicReset": deterministic_all,
        "blockedInputs": blocked_all,
    }
    out_root = private_dir(out_root)
    write_json(out_root / "auto-crawl-replay.json", result, sensitive_values=_sensitive_values(cfg))
    summary = [{
        "scenario": "auto_crawl", "platform": platform,
        "status": "passed" if baseline_graph.get("screens") else "failed",
        "error": None if baseline_graph.get("screens") else "Baseline graph has no screens",
        "actions": [],
        "crawler": {
            "baselineScreens": len(baseline_graph.get("screens", [])),
            "reproducedScreens": reproduced, "failedPaths": len(failures),
        },
    }]
    write_json(out_root / "run-summary.json", summary, sensitive_values=_sensitive_values(cfg))
    return result


def coverage_summary(baseline_graph, candidate_replay):
    """Both targets' reset/input/capture evidence determines validity, not just baseline count."""
    reset = _merge_reset(baseline_graph.get("deterministicReset"), candidate_replay.get("deterministicReset"))
    failures = candidate_replay.get("failedPaths", [])
    inputs = [*candidate_replay.get("blockedInputs", []),
              *(item for failure in failures for rec in failure.get("trace", []) for item in rec.get("blockedInputs", []))]
    branched = max(baseline_graph.get("attemptedPaths", 0), len(baseline_graph.get("screens", [])),
                   candidate_replay.get("baselineScreens", 0), candidate_replay.get("reproducedScreens", 0)+len(failures)) > 1
    expected = max(baseline_graph.get("discoveredScreens", 0), len(baseline_graph.get("screens", [])),
                   candidate_replay.get("baselineScreens", 0))
    incomplete = (baseline_graph.get("coverageStatus") != "COMPLETE_WITHIN_POLICY" or inputs
                  or failures or candidate_replay.get("reproducedScreens", 0) < expected
                  or (branched and reset is not True))
    return {
        "mode": "automatic", "discoveredBaselineScreens": int(baseline_graph.get("discoveredScreens", 0)),
        "candidateScreensReproduced": int(candidate_replay.get("reproducedScreens", 0)),
        "candidatePathFailures": len(failures), "baselineReplayFailures": len(baseline_graph.get("replayFailures", [])),
        "blockedUnsafeActions": len(baseline_graph.get("blockedActions", [])),
        "blockedInputs": len(baseline_graph.get("blockedInputs", [])) + len(inputs),
        "candidateBlockedInputs": len(inputs), "actionsTruncated": int(baseline_graph.get("actionsTruncated", 0)),
        "coverageStatus": "PARTIAL" if incomplete else "COMPLETE_WITHIN_POLICY",
        "resetIsolationStatus": _reset_status(reset),
        "baselineResetIsolationStatus": _reset_status(baseline_graph.get("deterministicReset")),
        "candidateResetIsolationStatus": _reset_status(candidate_replay.get("deterministicReset")),
        "depthFrontierReached": bool(baseline_graph.get("depthFrontierReached")),
        "limitReached": bool(baseline_graph.get("limitReached")), "coverageNote": baseline_graph.get("coverageNote"),
    }
