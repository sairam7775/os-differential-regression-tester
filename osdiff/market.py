"""Probe preinstalled physical-device apps and gate market-build comparisons.

Android origin uses package-manager metadata; iOS origin is operator attestation.
Exact marketing version and build must match before crawling. Market runtimes
omit the Appium app capability so the normal path preserves the installed binary.
Missing OS evidence and post-run app revalidation remain stabilization work.
"""

from __future__ import annotations

import hashlib
import platform
import re
import shutil
import subprocess
from pathlib import Path

from osdiff.fsutil import private_dir, write_json
from osdiff.devices import adb_path


def _run(cmd, timeout=30, check=True):
    """Run a bounded physical-device probe; checked errors include command/output detail."""
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(cmd)}") from exc
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


def _adb(serial, *args, timeout=30, check=True):
    """Target exactly one serial for each ADB probe; ADB currently resolves through PATH only."""
    adb = adb_path() or "adb"
    return _run([adb, "-s", serial, *args], timeout=timeout, check=check)


def list_android_devices():
    """Parse authorized adb devices -l entries; callers still need to reject emulators."""
    adb = adb_path() or "adb"
    out = _run([adb, "devices", "-l"], check=False)
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        meta = {}
        for token in parts[2:]:
            if ":" in token:
                k, v = token.split(":", 1)
                meta[k] = v
        devices.append({"serial": parts[0], **meta})
    return devices


def _android_is_emulator(serial):
    """Check emulator serial prefix and ro.kernel.qemu before physical-device market testing."""
    return serial.startswith("emulator-") or _adb(serial, "shell", "getprop", "ro.kernel.qemu", check=False).strip() == "1"


def _android_package_installed(serial, package_id):
    """Check pm path without installing, upgrading, or downgrading the target package."""
    return bool(_adb(serial, "shell", "pm", "path", package_id, check=False).strip())


def _android_pkg_dump(serial, package_id):
    """Read package-manager metadata for version/build extraction without modifying the app."""
    return _adb(serial, "shell", "dumpsys", "package", package_id, timeout=45, check=False)


def _extract_android_version(dump):
    """Return marketing versionName and numeric versionCode strings, or None when unavailable."""
    version_name = None
    version_code = None
    m = re.search(r"\bversionName=([^\s]+)", dump)
    if m:
        version_name = m.group(1)
    m = re.search(r"\bversionCode=(\d+)", dump)
    if m:
        version_code = m.group(1)
    return version_name, version_code


def _android_installer(serial, package_id):
    """Prefer installer-source metadata and fall back to pm list packages -i.
    
    This is metadata-based provenance, not cryptographic verification of a store
    receipt. The first available source label is used by the current parser."""
    raw = _adb(serial, "shell", "cmd", "package", "get-install-source", package_id, check=False)
    candidates = []
    for label in (
        "Installer package name", "Installing package name",
        "Initiating package name", "Originating package name",
    ):
        m = re.search(rf"{re.escape(label)}:\s*([^\s]+)", raw, re.I)
        if m and m.group(1).lower() != "null":
            candidates.append(m.group(1))
    if not candidates:
        fallback = _adb(serial, "shell", "pm", "list", "packages", "-i", package_id, check=False)
        m = re.search(r"installer=([^\s]+)", fallback)
        if m and m.group(1).lower() != "null":
            candidates.append(m.group(1))
    return candidates[0] if candidates else None, raw


def _android_launch_activity(serial, package_id):
    """Resolve a package launch component without launching or replacing its installed binary."""
    raw = _adb(serial, "shell", "cmd", "package", "resolve-activity", "--brief", package_id, check=False)
    for line in reversed([x.strip() for x in raw.splitlines() if x.strip()]):
        if "/" in line and package_id in line:
            return line.split("/", 1)[1]
    return None


def _android_orientation(serial):
    """Extract SurfaceOrientation when input-service diagnostics expose it."""
    raw = _adb(serial, "shell", "dumpsys", "input", check=False)
    m = re.search(r"SurfaceOrientation:\s*(\d+)", raw)
    return m.group(1) if m else None


def _android_environment(serial):
    """Collect comparable locale/timezone/font/display facts, preserving unavailable values."""
    locale = _adb(serial, "shell", "getprop", "persist.sys.locale", check=False).strip()
    if not locale:
        locale = _adb(serial, "shell", "getprop", "ro.product.locale", check=False).strip()
    return {
        "locale": locale or None,
        "timezone": _adb(serial, "shell", "getprop", "persist.sys.timezone", check=False).strip() or None,
        "fontScale": _adb(serial, "shell", "settings", "get", "system", "font_scale", check=False).strip() or None,
        "orientation": _android_orientation(serial),
        "uiMode": _adb(serial, "shell", "cmd", "uimode", "night", check=False).strip() or None,
        "screenSize": _adb(serial, "shell", "wm", "size", check=False).strip() or None,
        "screenDensity": _adb(serial, "shell", "wm", "density", check=False).strip() or None,
    }


def probe_android_market_device(serial, package_id, allowed_installers=None, app_activity=None):
    """Verify authorization/physical target and return installed app, OS, origin, and environment facts.
    
    All operations inspect the specified serial. Missing version/build fails pair
    validation; OS identity missingness still needs stricter checks."""
    allowed_installers = list(allowed_installers or ["com.android.vending"])
    connected = {d["serial"]: d for d in list_android_devices()}
    if serial not in connected:
        raise RuntimeError(f"Android device {serial!r} is not connected/authorized in adb.")
    if _android_is_emulator(serial):
        raise RuntimeError(f"{serial} is an emulator. market-run requires a physical Android device.")
    if not _android_package_installed(serial, package_id):
        raise RuntimeError(f"{package_id} is not installed on Android device {serial}.")

    dump = _android_pkg_dump(serial, package_id)
    version_name, version_code = _extract_android_version(dump)
    installer, installer_raw = _android_installer(serial, package_id)
    resolved_activity = app_activity or _android_launch_activity(serial, package_id)
    if not resolved_activity:
        raise RuntimeError("Unable to resolve Android launch activity. Supply --app-activity explicitly.")

    manufacturer = _adb(serial, "shell", "getprop", "ro.product.manufacturer", check=False)
    model = _adb(serial, "shell", "getprop", "ro.product.model", check=False)
    device = _adb(serial, "shell", "getprop", "ro.product.device", check=False)
    os_release = _adb(serial, "shell", "getprop", "ro.build.version.release", check=False)
    api_level = _adb(serial, "shell", "getprop", "ro.build.version.sdk", check=False)
    build_fp = _adb(serial, "shell", "getprop", "ro.build.fingerprint", check=False)
    security_patch = _adb(serial, "shell", "getprop", "ro.build.version.security_patch", check=False)
    build_id = _adb(serial, "shell", "getprop", "ro.build.id", check=False)
    incremental = _adb(serial, "shell", "getprop", "ro.build.version.incremental", check=False)
    environment = _android_environment(serial)

    return {
        "platform": "android", "physicalDevice": True, "deviceId": serial,
        "manufacturer": manufacturer, "model": model, "modelVerified": bool(model),
        "deviceName": device or model or "Android",
        "osVersion": os_release, "apiLevel": api_level,
        "securityPatch": security_patch or None, "buildFingerprint": build_fp or None,
        "buildId": build_id or None, "buildIncremental": incremental or None,
        "screenSize": environment.get("screenSize"), "environment": environment,
        "appId": package_id, "appVersion": version_name, "appBuild": version_code,
        "appActivity": resolved_activity, "installerPackage": installer,
        "allowedInstallers": allowed_installers,
        "marketOriginVerified": installer in allowed_installers,
        "marketOriginMethod": "Android package-manager installer metadata",
        "marketOriginRaw": installer_raw, "toolInstalledApp": False,
    }


def _normalize_ios_apps(raw):
    """Normalize supported listApps response shapes to a list of bundle attribute dictionaries."""
    if isinstance(raw, dict):
        if "applications" in raw and isinstance(raw["applications"], list):
            return raw["applications"]
        if raw and all(isinstance(v, dict) for v in raw.values()):
            out = []
            for bundle, attrs in raw.items():
                item = dict(attrs)
                item.setdefault("CFBundleIdentifier", bundle)
                out.append(item)
            return out
    if isinstance(raw, list):
        return raw
    return []


def _physical_ios_device_ids():
    """Read the host's physical-device section rather than infer physical from missing caps."""
    output = _run(["xcrun", "xctrace", "list", "devices"], timeout=30)
    devices, physical = set(), False
    for line in output.splitlines():
        if line.strip().startswith("=="):
            physical = line.strip().startswith("== Devices")
            continue
        if physical:
            match = re.search(r"\(([A-Za-z0-9-]{20,})\)\s*$", line)
            if match:
                devices.add(match.group(1))
    return devices


def _new_probe_session(server_url, runtime):
    from appium import webdriver
    from osdiff.runner import _options
    return webdriver.Remote(server_url, options=_options(runtime, "ios"))


def probe_ios_market_device(server_url, udid, bundle_id, app_store_confirmed=False):
    """Use a temporary XCUITest session to inspect one preinstalled physical-device app.
    
    The session is always quit after successful creation. Store origin is operator
    attestation; absent simulator metadata currently does not prove physical identity."""
    if platform.system() != "Darwin":
        raise RuntimeError("iOS real-device market testing requires macOS with Xcode.")
    if udid not in _physical_ios_device_ids():
        raise RuntimeError("iOS target is not verified as a physical device on this host")
    runtime = {"udid": udid, "deviceName": "iPhone", "preinstalled": True, "noReset": True}
    driver = _new_probe_session(server_url, runtime)
    try:
        caps = dict(driver.capabilities or {})
        try:
            info = driver.execute_script("mobile: deviceInfo", {}) or {}
        except Exception:
            info = {}
        if str(caps.get("isSimulator", "")).lower() == "true" or info.get("simulator"):
            raise RuntimeError(f"{udid} is a simulator. market-run requires a physical iOS device.")

        raw_apps = driver.execute_script(
            "mobile: listApps",
            {
                "applicationType": "User",
                "returnAttributes": [
                    "CFBundleIdentifier", "CFBundleName", "CFBundleDisplayName",
                    "CFBundleVersion", "CFBundleShortVersionString",
                ],
            },
        )
        apps = _normalize_ios_apps(raw_apps)
        app = next((x for x in apps if x.get("CFBundleIdentifier") == bundle_id), None)
        if not app:
            raise RuntimeError(f"{bundle_id} is not installed on iOS device {udid}.")

        product_type = info.get("productType") or info.get("ProductType")
        documented_model = info.get("model") or info.get("Model")
        model = product_type or documented_model or caps.get("deviceName") or "iPhone"
        generic_model = str(model).strip().lower() in {"iphone", "ipad", "ios device", "unknown", ""}
        name = info.get("name") or info.get("deviceName") or info.get("DeviceName") or caps.get("deviceName") or model
        try:
            size = driver.get_window_size()
            screen_size = f"{size.get('width')}x{size.get('height')}"
        except Exception:
            screen_size = None
        environment = {
            "locale": info.get("locale") or caps.get("locale"),
            "timezone": info.get("timeZone") or info.get("timezone"),
            "appearance": info.get("appearance") or info.get("userInterfaceStyle"),
            "screenSize": screen_size,
        }
        return {
            "platform": "ios", "physicalDevice": True, "deviceId": udid,
            "manufacturer": "Apple", "model": model, "modelVerified": not generic_model,
            "deviceName": name,
            "osVersion": str(caps.get("platformVersion") or info.get("productVersion") or info.get("ProductVersion") or "unknown"),
            "apiLevel": None,
            "securityPatch": None,
            "buildFingerprint": info.get("buildVersion") or info.get("BuildVersion"),
            "screenSize": screen_size, "environment": environment,
            "appId": bundle_id,
            "appVersion": app.get("CFBundleShortVersionString"),
            "appBuild": app.get("CFBundleVersion"),
            "installerPackage": None,
            "marketOriginVerified": bool(app_store_confirmed),
            "marketOriginMethod": (
                "Operator App Store installation attestation; bundle/version/build verified "
                "from the preinstalled app via XCUITest"
            ),
            "marketOriginRaw": None, "toolInstalledApp": False,
        }
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _os_identity(device):
    """OS-only identity; manufacturer/product/device portions of Android fingerprints are excluded."""
    def known(value):
        text = str(value or "").strip()
        return "" if text.lower() in {"unknown", "null", "none", "n/a"} else text
    build = known(device.get("buildId"))
    incremental = known(device.get("buildIncremental"))
    if device.get("platform") == "android":
        match = re.match(r"[^/]+/[^/]+/[^:]+:([^/]+)/([^/]+)/([^:]+):", known(device.get("buildFingerprint")))
        if match:
            build = build or known(match.group(2))
            incremental = incremental or known(match.group(3))
    else:
        build = build or known(device.get("buildFingerprint"))
    return tuple(known(device.get(key)) for key in ("osVersion", "apiLevel", "securityPatch")) + (build, incremental)


def _environment_differences(baseline, candidate):
    """Compare only environment fields exposed on both devices; unknown fields are skipped."""
    b = baseline.get("environment") or {}
    c = candidate.get("environment") or {}
    differences = []
    for key in sorted(set(b) | set(c)):
        bv, cv = b.get(key), c.get(key)
        if bv in (None, "") or cv in (None, ""):
            continue
        if str(bv) != str(cv):
            differences.append({"key": key, "baseline": bv, "candidate": cv})
    return differences


def validate_market_pair(baseline, candidate, require_same_model=False, require_matching_environment=True):
    """Return gate validity, error labels, warnings, and app/model/environment comparison evidence.
    
    Version and build matching is mandatory. Model/environment policies can be
    configured; missing OS fields currently can create a false difference, and
    physicalDevice is assumed from the probe rather than rechecked here."""
    errors, warnings = [], []
    if not baseline.get("deviceId") or not candidate.get("deviceId"):
        errors.append("device_identity_unavailable")
    if baseline.get("physicalDevice") is not True or candidate.get("physicalDevice") is not True:
        errors.append("physical_device_not_verified")
    if not baseline.get("appId") or not candidate.get("appId"):
        errors.append("app_id_unavailable")
    if baseline.get("deviceId") == candidate.get("deviceId"):
        errors.append("baseline_and_candidate_device_ids_must_differ")
    if baseline.get("platform") != candidate.get("platform"):
        errors.append("platform_mismatch")
    if baseline.get("appId") != candidate.get("appId"):
        errors.append("app_id_mismatch")

    bver, cver = baseline.get("appVersion"), candidate.get("appVersion")
    bbuild, cbuild = baseline.get("appBuild"), candidate.get("appBuild")
    if not bver or not cver:
        errors.append("app_version_unavailable")
    elif bver != cver:
        errors.append("app_version_mismatch")
    if not bbuild or not cbuild:
        errors.append("app_build_unavailable")
    elif str(bbuild) != str(cbuild):
        errors.append("app_build_mismatch")

    pairs = [(a, b) for a, b in zip(_os_identity(baseline), _os_identity(candidate)) if a and b]
    if not pairs:
        errors.append("os_identity_unavailable")
    if not any(a != b for a, b in pairs):
        errors.append("os_identity_must_differ")
    if not baseline.get("marketOriginVerified"):
        errors.append("baseline_market_origin_not_verified")
    if not candidate.get("marketOriginVerified"):
        errors.append("candidate_market_origin_not_verified")

    same_model = (
        str(baseline.get("manufacturer", "")).lower() == str(candidate.get("manufacturer", "")).lower()
        and str(baseline.get("model", "")).lower() == str(candidate.get("model", "")).lower()
    )
    models_verified = bool(baseline.get("modelVerified", True) and candidate.get("modelVerified", True))
    if not models_verified:
        if require_same_model:
            errors.append("hardware_model_unverified")
        else:
            warnings.append("Hardware model could not be verified precisely on one or both devices.")
    elif not same_model:
        if require_same_model:
            errors.append("hardware_model_mismatch")
        else:
            warnings.append("Hardware models differ; UI/performance differences may be caused by hardware as well as OS.")

    environment_differences = _environment_differences(baseline, candidate)
    if environment_differences:
        if require_matching_environment:
            errors.extend(f"environment_mismatch:{item['key']}" for item in environment_differences)
        else:
            warnings.append("Device environment differs: " + ", ".join(item["key"] for item in environment_differences))

    same_app = bool(bver and cver and bbuild and cbuild and bver == cver and str(bbuild) == str(cbuild))
    return {
        "valid": not errors, "errors": errors, "warnings": warnings,
        "sameHardwareModel": same_model and models_verified,
        "sameAppVersionAndBuild": same_app,
        "environmentDifferences": environment_differences,
        "baselineOsIdentity": _os_identity(baseline),
        "candidateOsIdentity": _os_identity(candidate),
    }


def market_runtime(device, platform_name, *, reset_strategy=None, reset_command=None):
    """Build a preinstalled target runtime without an app binary and choose its reset strategy.
    
    Android defaults to data clear; real iOS defaults to non-deterministic relaunch.
    An operator reset command overrides the chosen strategy."""
    runtime = {
        "udid": device["deviceId"],
        "deviceName": device.get("deviceName") or device.get("model") or platform_name,
        "appPath": None, "preinstalled": True, "noReset": True,
        "checkpointSettleSeconds": 0.25,
    }
    if platform_name == "android":
        runtime.update(
            appPackage=device["appId"], appActivity=device.get("appActivity"),
            autoGrantPermissions=False,
            adbPath=adb_path(),
            resetStrategy=reset_strategy or "android_clear_data",
        )
    else:
        runtime.update(
            bundleId=device["appId"],
            resetStrategy=reset_strategy or "relaunch",
        )
    if reset_command:
        runtime["resetStrategy"] = "reset_command"
        runtime["resetCommand"] = list(reset_command)
    return runtime


def _sanitized_device(device):
    """Mask/hash the primary device ID and drop raw installer output for persisted provenance.
    
    This does not sanitize exceptions, traces, or arbitrary metadata elsewhere."""
    item = dict(device)
    device_id = str(item.pop("deviceId", "") or "")
    if device_id:
        item["deviceIdMasked"] = (device_id[:4] + "…" + device_id[-4:]) if len(device_id) > 10 else "<redacted>"
        item["deviceIdSha256"] = hashlib.sha256(device_id.encode("utf-8")).hexdigest()
    item.pop("marketOriginRaw", None)
    return item


def validate_market_pair_after_run(baseline, candidate, final_baseline, final_candidate, **policy):
    """Reject store updates, OS changes, or target changes between preflight and capture."""
    validation = validate_market_pair(final_baseline, final_candidate, **policy)
    for role, before, after in (("baseline", baseline, final_baseline), ("candidate", candidate, final_candidate)):
        if any(str(before.get(key)) != str(after.get(key)) for key in ("appId", "appVersion", "appBuild")):
            validation["errors"].append(f"{role}_app_changed_during_run")
        if before.get("deviceId") != after.get("deviceId"):
            validation["errors"].append(f"{role}_device_changed_during_run")
        if _os_identity(before) != _os_identity(after):
            validation["errors"].append(f"{role}_os_changed_during_run")
    validation["valid"] = not validation["errors"]
    validation["postRunIdentityVerified"] = validation["valid"]
    return validation


def write_provenance(path, baseline, candidate, validation):
    """Persist sanitized baseline/candidate facts and validation under the real-device market mode."""
    data = {
        "mode": "real-device-market-build", "toolInstalledApp": False,
        "baseline": _sanitized_device(baseline),
        "candidate": _sanitized_device(candidate),
        "validation": validation,
    }
    target = Path(path)
    private_dir(target.parent)
    write_json(target, data)
    return data
