from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path

from osdiff.fsutil import mask_image_regions, private_dir, private_file, redact_values, write_json, write_text

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait


def _loc(platform, spec):
    if platform in spec:
        spec = spec[platform]
    strategy = spec["strategy"]
    value = spec["value"]
    mapping = {
        "accessibility_id": AppiumBy.ACCESSIBILITY_ID,
        "id": AppiumBy.ID,
        "xpath": AppiumBy.XPATH,
        "class_name": AppiumBy.CLASS_NAME,
        "android_uiautomator": AppiumBy.ANDROID_UIAUTOMATOR,
        "ios_predicate": AppiumBy.IOS_PREDICATE,
        "ios_class_chain": AppiumBy.IOS_CLASS_CHAIN,
    }
    if strategy not in mapping:
        raise ValueError(f"Unsupported locator strategy: {strategy}")
    return mapping[strategy], value


def _find(driver, platform, locator, timeout=10):
    by, value = _loc(platform, locator)
    return WebDriverWait(driver, timeout).until(lambda d: d.find_element(by, value))


def _assertion(driver, platform, assertion):
    result = {"type": assertion.get("type"), "passed": False, "message": ""}
    try:
        typ = assertion["type"]
        element = _find(
            driver,
            platform,
            assertion["locator"],
            assertion.get("timeout", 5),
        )
        if typ == "element_present":
            result.update(passed=True, message="Element present")
        elif typ == "text_equals":
            expected = os.path.expandvars(str(assertion.get("value", "")))
            actual = element.text or ""
            result.update(
                passed=(actual == expected),
                message=f"expected={expected!r}; actual={actual!r}",
            )
        elif typ == "enabled":
            expected = bool(assertion.get("value", True))
            actual = bool(element.is_enabled())
            result.update(
                passed=(actual == expected),
                message=f"expected={expected}; actual={actual}",
            )
        elif typ == "displayed":
            expected = bool(assertion.get("value", True))
            actual = bool(element.is_displayed())
            result.update(
                passed=(actual == expected),
                message=f"expected={expected}; actual={actual}",
            )
        else:
            result["message"] = f"Unsupported assertion: {typ}"
    except Exception as exc:
        result["message"] = f"{type(exc).__name__}: {exc}"
    return result


def _options(runtime, platform):
    """Build Appium options.

    In market/preinstalled mode, intentionally omit the `app` capability so Appium
    never installs or replaces the application under test. The session launches the
    already-installed store build by package/bundle identifier.
    """
    preinstalled = bool(runtime.get("preinstalled", False))
    app_path = runtime.get("appPath")
    app = str(Path(app_path).resolve()) if app_path else None

    if platform == "android":
        opt = UiAutomator2Options()
        opt.platform_name = "Android"
        opt.automation_name = "UiAutomator2"
        opt.device_name = runtime.get("deviceName", "Android")
        opt.udid = runtime["udid"]
        if not preinstalled and app:
            opt.app = app
        if runtime.get("appPackage"):
            opt.app_package = runtime["appPackage"]
        if runtime.get("appActivity"):
            opt.app_activity = runtime["appActivity"]
        opt.auto_grant_permissions = bool(runtime.get("autoGrantPermissions", False))
        opt.no_reset = bool(runtime.get("noReset", preinstalled))
        return opt

    opt = XCUITestOptions()
    opt.platform_name = "iOS"
    opt.automation_name = "XCUITest"
    opt.device_name = runtime.get("deviceName", "iPhone")
    opt.udid = runtime["udid"]
    if not preinstalled and app:
        opt.app = app
    if runtime.get("bundleId"):
        opt.bundle_id = runtime["bundleId"]
    opt.no_reset = bool(runtime.get("noReset", preinstalled))
    return opt


def _execute(driver, platform, step):
    typ = step["type"]
    if typ == "tap":
        _find(driver, platform, step["locator"], step.get("timeout", 10)).click()
    elif typ == "type_text":
        element = _find(driver, platform, step["locator"], step.get("timeout", 10))
        if step.get("clear", True):
            try:
                element.clear()
            except Exception:
                pass
        element.send_keys(os.path.expandvars(str(step.get("text", ""))))
    elif typ == "wait_for":
        _find(driver, platform, step["locator"], step.get("timeout", 10))
    elif typ == "sleep":
        time.sleep(float(step.get("seconds", 1)))
    elif typ == "back":
        driver.back()
    elif typ == "swipe":
        size = driver.get_window_size()
        driver.swipe(
            int(size["width"] * float(step.get("startX", 0.5))),
            int(size["height"] * float(step.get("startY", 0.8))),
            int(size["width"] * float(step.get("endX", 0.5))),
            int(size["height"] * float(step.get("endY", 0.2))),
            int(step.get("durationMs", 500)),
        )
    elif typ == "terminate_app":
        driver.terminate_app(step["appId"])
    elif typ == "activate_app":
        driver.activate_app(step["appId"])
    else:
        raise ValueError(f"Unsupported step type: {typ}")


def _checkpoint(driver, platform, scenario_name, step, actions, out_root, settle_seconds, sensitive_env_names=None, sensitive_regions=None):
    folder = private_dir(out_root / scenario_name / step["id"])

    # Assertions act as readiness checks. Capture only after they have completed,
    # otherwise the screenshot/source can represent a transitional screen.
    assertions = [
        _assertion(driver, platform, assertion)
        for assertion in step.get("assertions", [])
    ]
    time.sleep(max(0.0, float(step.get("settleSeconds", settle_seconds))))

    screenshot = folder / "screen.png"
    driver.save_screenshot(str(screenshot))
    mask_image_regions(screenshot, (sensitive_regions or {}).get(platform, []))
    private_file(screenshot)
    source = driver.page_source or ""
    secrets = [os.getenv(name) for name in (sensitive_env_names or []) if os.getenv(name)]
    write_text(folder / "source.xml", redact_values(source, secrets))
    state = {
        "scenario": scenario_name,
        "checkpoint": step["id"],
        "platform": platform,
        "assertions": assertions,
        "recentActions": actions,
        "windowSize": driver.get_window_size(),
        "capturedEpoch": time.time(),
    }
    write_json(folder / "state.json", state)


def run_scenario(server_url, runtime, platform, scenario, out_root):
    driver = None
    run = {
        "scenario": scenario["name"],
        "status": "running",
        "error": None,
        "actions": [],
        "checkpointsCaptured": [],
        "completedSteps": 0,
    }
    recent = []
    try:
        driver = webdriver.Remote(server_url, options=_options(runtime, platform))
        for step in scenario["steps"]:
            if step.get("platforms") and platform not in step["platforms"]:
                continue
            if step["type"] == "checkpoint":
                _checkpoint(
                    driver,
                    platform,
                    scenario["name"],
                    step,
                    recent,
                    out_root,
                    runtime.get("checkpointSettleSeconds", 0.25),
                    runtime.get("sensitiveEnvNames", ["TEST_USER_EMAIL", "TEST_USER_PASSWORD"]),
                    runtime.get("sensitiveRegions", {}),
                )
                run["checkpointsCaptured"].append(step["id"])
                run["completedSteps"] += 1
                recent = []
                continue

            rec = {"type": step["type"], "status": "running", "error": None}
            start = time.time()
            try:
                _execute(driver, platform, step)
                rec["status"] = "passed"
            except Exception as exc:
                rec["status"] = "failed"
                rec["error"] = f"{type(exc).__name__}: {exc}"
                if not step.get("continueOnFailure", False):
                    raise
            finally:
                rec["durationSeconds"] = round(time.time() - start, 3)
                run["actions"].append(rec)
                recent.append(rec)
                run["completedSteps"] += 1
        run["status"] = "passed"
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = f"{type(exc).__name__}: {exc}"
        run["traceback"] = traceback.format_exc()
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
    return run


def run_target(server_url, runtime, platform, scenarios, output):
    out = private_dir(output)
    summary = []
    for scenario_path in scenarios:
        scenario = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
        if platform not in scenario.get("platforms", [platform]):
            continue
        summary.append(run_scenario(server_url, runtime, platform, scenario, out))
    write_json(out / "run-summary.json", summary)
    return summary
