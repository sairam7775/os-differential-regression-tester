"""Discover baseline UI states and replay their navigation paths on a candidate.

Each queued path starts with the configured app-state reset. One Appium session
is reused per phase and discarded after a replay error. Actions store locator
candidates, ordinals, and bounds; these are not proof of safe live targeting.
The imported baseline has unresolved locator/safety and reset-evidence gaps.
See docs/AUTO_DISCOVERY.md and docs/BASELINE_ASSESSMENT.md before changing it.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from collections import deque
from pathlib import Path
from xml.etree import ElementTree as ET

from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy

from osdiff.fsutil import mask_image_regions, private_dir, private_file, redact_values, write_json, write_text
from osdiff.runner import _options

DEFAULT_ANDROID_SYSTEM_PACKAGES = {
    "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
    "com.android.packageinstaller",
    "com.google.android.providers.media.module",
    "com.android.providers.media.module",
    "com.android.settings",
    "com.google.android.documentsui",
    "com.android.documentsui",
}

DEFAULT_IOS_SYSTEM_BUNDLES = {
    "com.apple.springboard",
    "com.apple.Preferences",
    "com.apple.mobileslideshow",
    "com.apple.DocumentsApp",
}


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
    """Return the first deny-pattern reason; allowKeywords never override a deny."""
    text = str(text or "")
    for deny in cfg.get("denyKeywords", []):
        if re.search(deny, text, re.I):
            return f"blocked_by_keyword:{deny}"
    # allowKeywords are retained only as positive metadata; they never override denies.
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
    """Hash normalized UI plus supplied foreground context into a 16-character state key.
    
    Transient iOS pid is currently included by callers, so relaunches can generate
    new keys for the same screen. This is a discovery identity, not a safety proof."""
    normalized = _normalize_for_fingerprint(source, cfg)
    if context:
        normalized += "\n@context:" + "|".join(f"{k}={context[k]}" for k in sorted(context) if context[k])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def discover_actions(source, platform, cfg):
    """Return (safe candidate actions, blocked reasons, input fields) from hierarchy XML.
    
    Actions contain kind, label, locator candidates, ordinal, and bounds. Ordinals
    currently count filtered controls, which can resolve to a different unsafe live
    control. Read the baseline assessment before trusting automatic clicks."""
    root = _xml_root(source)
    if root is None:
        return [], [{"label": "(hierarchy)", "reason": "hierarchy_parse_failed"}], []

    actions, blocked, input_nodes = [], [], []
    seen = {}
    has_scrollable = False
    for node in root.iter():
        attrs = node.attrib
        bounds = _bounds_android(attrs.get("bounds")) if platform == "android" else _bounds_ios(attrs)
        if _is_input(platform, attrs):
            input_nodes.append({
                "label": _label(platform, attrs),
                "locators": _locators(platform, attrs),
                "bounds": bounds,
                "secure": attrs.get("type") == "XCUIElementTypeSecureTextField" or "password" in _label(platform, attrs).lower(),
            })
        if _is_scrollable(platform, attrs):
            has_scrollable = True
        if not _is_actionable(platform, attrs) or not bounds:
            continue

        label = _label(platform, attrs)
        locators = _locators(platform, attrs)
        if not locators and not label:
            blocked.append({"label": "(unidentified control)", "reason": "no_stable_locator"})
            continue

        reason = _danger_reason(label + " " + " ".join(l.get("value", "") for l in locators), cfg)
        if cfg.get("safeMode", True) and reason:
            blocked.append({"label": label or "(unnamed)", "reason": reason})
            continue

        primary = locators[0] if locators else {"strategy": "coordinate", "value": ""}
        dedupe_base = f"{primary.get('strategy')}|{primary.get('value')}"
        ordinal = seen.get(dedupe_base, 0)
        seen[dedupe_base] = ordinal + 1
        actions.append({"kind": "tap", "label": label or "(unnamed)", "locators": locators, "ordinal": ordinal, "bounds": bounds})

    if has_scrollable and cfg.get("enableScrolling", True):
        actions.append({"kind": "scroll_down", "label": "Scroll down"})

    actions.sort(key=lambda a: (
        a.get("kind") == "scroll_down",
        0 if any(l.get("strategy") in ("id", "accessibility_id") for l in a.get("locators", [])) else 1,
        a.get("label", ""),
    ))
    max_actions = int(cfg.get("maxActionsPerScreen", 24))
    if len(actions) > max_actions:
        blocked.append({
            "label": "(action limit)", "reason": "actions_truncated",
            "totalActions": len(actions), "exploredActions": max_actions,
        })
    return actions[:max_actions], blocked, input_nodes


def _find_elements(driver, locator):
    """Query a locator and collapse exceptions to no matches; transport errors lose their cause."""
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
    """Try locator candidates using one stored ordinal across their full live match sets.
    
    Missing occurrences return None. Filtered-vs-live ordinals and fallback match-set
    differences remain a confirmed safe-mode targeting defect."""
    ordinal = int(action.get("ordinal", 0))
    for locator in action.get("locators", []):
        matches = _find_elements(driver, locator)
        if ordinal < len(matches):
            return matches[ordinal]
    return None


def _tap(driver, platform, action):
    """Try element click, native gesture, then coordinates only when no locators were recorded.
    
    The resolved element is not rechecked against safety policy here. Gesture
    fallback can retry after a click exception; avoid interpreting this as idempotent."""
    element = _find_for_action(driver, action)
    if element is not None:
        try:
            element.click()
            return
        except Exception:
            try:
                if platform == "android":
                    driver.execute_script("mobile: clickGesture", {"elementId": element.id})
                else:
                    driver.execute_script("mobile: tap", {"elementId": element.id, "x": 1, "y": 1})
                return
            except Exception:
                pass

    # Coordinate fallback is allowed only for controls that had no stable locator.
    if action.get("locators"):
        raise RuntimeError(f"Expected control occurrence not found: {action.get('label')}")
    bounds = action.get("bounds") or {}
    x = int(bounds.get("x", 0) + bounds.get("width", 0) / 2)
    y = int(bounds.get("y", 0) + bounds.get("height", 0) / 2)
    if x <= 0 or y <= 0:
        raise RuntimeError(f"Unable to locate action: {action.get('label')}")
    if platform == "android":
        driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
    else:
        driver.execute_script("mobile: tap", {"x": x, "y": y})


def _scroll(driver, platform):
    """Swipe downward through the visible window; no container or scroll-end evidence is returned."""
    size = driver.get_window_size()
    x = int(size["width"] * 0.5)
    driver.swipe(x, int(size["height"] * 0.78), x, int(size["height"] * 0.25), 450)


def execute_action(driver, platform, action, settle_seconds=0.5):
    """Execute a tap/down-scroll and sleep for stabilization; foreground checking belongs to replay."""
    if action["kind"] == "tap":
        _tap(driver, platform, action)
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


def fill_known_inputs(driver, platform, source, cfg):
    """Fill recognized fields and return metadata plus blocked reasons without storing input values.
    
    Duplicate fields currently use ordinal zero; failed clearing is ignored. Inline
    rule values also need complete redaction coverage before production use."""
    _, _, inputs = discover_actions(source, platform, cfg)
    rules = cfg.get("autoInputRules", [])
    filled, blocked = [], []
    for field in inputs:
        haystack = field.get("label", "")
        rule = next((r for r in rules if re.search(r.get("pattern", "$^"), haystack, re.I)), None)
        if not rule:
            blocked.append({"label": haystack or "(input)", "reason": "no_auto_input_rule"})
            continue
        value = _input_value(rule)
        if value in (None, ""):
            blocked.append({"label": haystack or "(input)", "reason": f"missing_input_value:{rule.get('env','inline')}"})
            continue
        element = _find_for_action(driver, {"locators": field.get("locators", []), "ordinal": 0})
        if element is None:
            blocked.append({"label": haystack or "(input)", "reason": "input_not_found"})
            continue
        try:
            try:
                element.clear()
            except Exception:
                pass
            element.send_keys(str(value))
            filled.append({"label": haystack or "(input)", "source": rule.get("env", "inline")})
        except Exception as exc:
            blocked.append({"label": haystack or "(input)", "reason": f"input_failed:{type(exc).__name__}"})
    return filled, blocked


def _sensitive_values(cfg):
    """Collect configured secrets and environment-backed input values for literal redaction."""
    values = list(cfg.get("sensitiveValues", []))
    for rule in cfg.get("autoInputRules", []):
        env_name = rule.get("env")
        if env_name and os.getenv(env_name):
            values.append(os.getenv(env_name))
    return [v for v in values if v]


def _redact_source(source, cfg):
    """Apply literal hierarchy redaction; the current replacement can make XML invalid."""
    return redact_values(source, _sensitive_values(cfg))


def _save_checkpoint(driver, platform, checkpoint, state_id, path_actions, out_root, cfg, metadata=None, recent_actions=None):
    """Persist a screenshot, source.xml, and state.json under auto_crawl/checkpoint.
    
    Screenshot masks are storage privacy masks. Source redaction currently breaks XML
    attributes; path/trace/metadata fields require additional secret sanitization."""
    folder = private_dir(Path(out_root) / "auto_crawl" / checkpoint)
    screenshot = folder / "screen.png"
    driver.save_screenshot(str(screenshot))
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
    write_json(folder / "state.json", state)
    return source


def _new_driver(server_url, runtime, platform):
    """Create a target-specific Appium session using runner's shared capability construction."""
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
    """Require a known target app or built-in/configured system surface after reset/action.
    
    Configured packages extend built-in allowances. after_activation currently does
    not tighten the policy; an allowed system surface may satisfy this check."""
    context = _foreground_context(driver, platform)
    if platform == "android":
        expected = runtime.get("appPackage")
        current = context.get("package")
        allowed = set(DEFAULT_ANDROID_SYSTEM_PACKAGES)
        allowed.update(cfg.get("allowedSystemPackages", {}).get("android", []))
    else:
        expected = runtime.get("bundleId")
        current = context.get("bundleId")
        allowed = set(DEFAULT_IOS_SYSTEM_BUNDLES)
        allowed.update(cfg.get("allowedSystemPackages", {}).get("ios", []))
    if not current:
        raise RuntimeError("Unable to determine the foreground application")
    if current == expected:
        return context
    if current in allowed:
        return context
    raise RuntimeError(f"Navigation left target app: active={current!r}, expected={expected!r}")


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
        if platform != "ios" or not runtime.get("appPath"):
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
    """Return (driver, action trace, error, deterministic reset) after replay from launch.
    
    A caller-supplied driver remains caller-owned on failure. If this function
    created the driver, it quits on replay failure and transfers ownership on success.
    Session creation errors occur before the replay try block."""
    owns_driver = driver is None
    if driver is None:
        driver = _new_driver(server_url, runtime, platform)
    trace = []
    try:
        deterministic = _prepare_path(driver, runtime, platform, cfg)
        settle = float(cfg.get("settleSeconds", 0.6))
        for index, action in enumerate(path_actions):
            source = driver.page_source or ""
            filled, blocked_inputs = fill_known_inputs(driver, platform, source, cfg)
            started = time.time()
            rec = {
                "index": index, "action": action, "status": "running",
                "durationSeconds": 0.0, "inputsFilled": filled, "blockedInputs": blocked_inputs,
            }
            try:
                execute_action(driver, platform, action, settle)
                _assert_allowed_foreground(driver, platform, runtime, cfg)
                rec["status"] = "passed"
            except Exception as exc:
                rec["status"] = "failed"
                rec["error"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                rec["durationSeconds"] = round(time.time() - started, 3)
                trace.append(rec)
        return driver, trace, None, deterministic
    except Exception as exc:
        if owns_driver:
            try:
                driver.quit()
            except Exception:
                pass
        return None, trace, f"{type(exc).__name__}: {exc}", False


def _close_driver(driver):
    """Best-effort Appium quit; callers own deciding when a failed session must be replaced."""
    if driver:
        try:
            driver.quit()
        except Exception:
            pass


def crawl_baseline(server_url, runtime, platform, out_root, cfg):
    """Breadth-first traversal of reset-to-launch action paths with checkpoint/graph persistence.
    
    First-seen fingerprints keep one representative path. Blocked/failed/truncated
    branches and exhausted limits force PARTIAL; intermediate input and stable-state
    checks still have gaps. Edges currently lack resolved destination state IDs."""
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
            if driver is None:
                driver = _new_driver(server_url, runtime, platform)
            used_driver, trace, replay_error, deterministic = replay_path(
                server_url, runtime, platform, path_actions, cfg, driver=driver
            )
            graph["deterministicReset"] = graph["deterministicReset"] and deterministic
            if used_driver is None:
                graph["replayFailures"].append({"path": path_actions, "error": replay_error, "trace": trace})
                _close_driver(driver)
                driver = None
                continue
            driver = used_driver
            time.sleep(settle)
            source = driver.page_source or ""
            context = _foreground_context(driver, platform)
            state_id = state_fingerprint(source, cfg, context)
            if state_id in visited:
                continue

            checkpoint = f"screen_{len(visited)+1:04d}_{state_id[:8]}"
            visited[state_id] = checkpoint
            filled, blocked_inputs = fill_known_inputs(driver, platform, source, cfg)
            if filled:
                time.sleep(float(cfg.get("afterInputSettleSeconds", 0.3)))
                source = driver.page_source or ""

            actions, blocked, _ = discover_actions(source, platform, cfg)
            graph["actionsTruncated"] += sum(1 for item in blocked if item.get("reason") == "actions_truncated")
            _save_checkpoint(
                driver, platform, checkpoint, state_id, path_actions, out_root, cfg,
                metadata={
                    "depth": len(path_actions), "actionsDiscovered": len(actions),
                    "inputsFilled": filled, "blockedInputs": blocked_inputs,
                    "foreground": context,
                },
                recent_actions=trace,
            )
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
                child_path = path_actions + [action]
                queue.append(child_path)
                graph["edges"].append({"from": checkpoint, "action": action, "depth": len(child_path)})
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
    graph["resetIsolationStatus"] = "DETERMINISTIC" if graph["deterministicReset"] else "NON_DETERMINISTIC"
    graph["coverageNote"] = (
        "Coverage means all UI states reachable from launch under the current crawler policy, credentials/test data, "
        "reset strategy and configured limits. Replay failures, blocked/truncated actions, missing inputs, or a non-"
        "deterministic reset strategy force PARTIAL coverage."
    )

    out_root = private_dir(out_root)
    write_json(out_root / "auto-crawl-graph.json", graph)
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
    write_json(out_root / "run-summary.json", summary)
    return graph


def replay_candidate_graph(server_url, runtime, platform, baseline_graph, out_root, cfg):
    """Replay baseline screen paths and capture candidate artifacts under baseline checkpoint names.
    
    reproducedScreens counts captures, not confirmed equivalent destinations. Failed
    paths are retained separately; the returned reset flag is not fully propagated
    by coverage_summary in this baseline."""
    reproduced, failures = 0, []
    driver = None
    deterministic_all = True
    try:
        for screen in baseline_graph.get("screens", []):
            checkpoint = screen["checkpoint"]
            path_actions = screen.get("path", [])
            if driver is None:
                driver = _new_driver(server_url, runtime, platform)
            used_driver, trace, error, deterministic = replay_path(
                server_url, runtime, platform, path_actions, cfg, driver=driver
            )
            deterministic_all = deterministic_all and deterministic
            if used_driver is None:
                failures.append({"checkpoint": checkpoint, "error": error, "path": path_actions, "trace": trace})
                _close_driver(driver)
                driver = None
                continue
            driver = used_driver
            time.sleep(float(cfg.get("settleSeconds", 0.6)))
            source = driver.page_source or ""
            filled, blocked_inputs = fill_known_inputs(driver, platform, source, cfg)
            if filled:
                time.sleep(float(cfg.get("afterInputSettleSeconds", 0.3)))
                source = driver.page_source or ""
            context = _foreground_context(driver, platform)
            state_id = state_fingerprint(source, cfg, context)
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
            reproduced += 1
    finally:
        _close_driver(driver)

    result = {
        "platform": platform, "mode": "candidate_replay",
        "baselineScreens": len(baseline_graph.get("screens", [])),
        "reproducedScreens": reproduced, "failedPaths": failures,
        "deterministicReset": deterministic_all,
    }
    out_root = private_dir(out_root)
    write_json(out_root / "auto-crawl-replay.json", result)
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
    write_json(out_root / "run-summary.json", summary)
    return result


def coverage_summary(baseline_graph, candidate_replay):
    """Combine discovery/replay counts for reporting using baseline coverage and reset status.
    
    Candidate path failures are regression evidence. Candidate non-deterministic
    resets and blocked inputs still need to affect validity during stabilization."""
    return {
        "mode": "automatic",
        "discoveredBaselineScreens": int(baseline_graph.get("discoveredScreens", 0)),
        "candidateScreensReproduced": int(candidate_replay.get("reproducedScreens", 0)),
        "candidatePathFailures": len(candidate_replay.get("failedPaths", [])),
        "baselineReplayFailures": len(baseline_graph.get("replayFailures", [])),
        "blockedUnsafeActions": len(baseline_graph.get("blockedActions", [])),
        "blockedInputs": len(baseline_graph.get("blockedInputs", [])),
        "actionsTruncated": int(baseline_graph.get("actionsTruncated", 0)),
        "coverageStatus": baseline_graph.get("coverageStatus", "PARTIAL"),
        "resetIsolationStatus": baseline_graph.get("resetIsolationStatus", "UNKNOWN"),
        "depthFrontierReached": bool(baseline_graph.get("depthFrontierReached")),
        "limitReached": bool(baseline_graph.get("limitReached")),
        "coverageNote": baseline_graph.get("coverageNote"),
    }
