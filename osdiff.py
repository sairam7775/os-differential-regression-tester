#!/usr/bin/env python3
"""Command-line orchestration for OS differential comparisons.

Market mode inspects two preinstalled physical-device builds. Virtual modes
provision emulators/simulators and use an operator-supplied binary. This module
owns Appium process handles, run directories, report generation, and exit codes.
See docs/DEVELOPER_GUIDE.md for the call graph and docs/BASELINE_ASSESSMENT.md
for unresolved validity, locking, and privacy issues in the imported baseline.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL_ROOT = HERE
sys.path.insert(0, str(TOOL_ROOT))

from osdiff import devices
from osdiff.fsutil import private_dir, redact_values, write_json


_RUN_LOCK_HANDLES = {}

def compare_platform(*args, **kwargs):
    # Help/doctor/listing must remain usable before optional image dependencies are installed.
    from osdiff.compare import compare_platform as compare
    return compare(*args, **kwargs)

def write_report(*args, **kwargs):
    from osdiff.compare import write_report as report
    return report(*args, **kwargs)

def _file_lock(fd, unlock=False):
    """Kernel ownership replaces unsafe PID polling and survives process crashes."""
    os.lseek(fd, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB)

def load_config(path):
    """Read JSON and attach the absolute config path/directory for relative resolution."""
    p = Path(path).resolve()
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg["_configPath"] = str(p)
    cfg["_configDir"] = str(p.parent)
    return cfg


def resolve_path(cfg, value):
    """Expand user/environment references; resolve relative paths beside the config file."""
    p = Path(os.path.expandvars(str(value))).expanduser()
    if p.is_absolute():
        return str(p.resolve())
    base = Path(cfg.get("_configDir", TOOL_ROOT))
    return str((base / p).resolve())


def command_exists(cmd):
    """Check PATH availability only; this does not prove the command can execute."""
    return shutil.which(cmd) is not None


def appium_bin():
    """Prefer the tool-local Appium launcher, then fall back to PATH."""
    local = (
        TOOL_ROOT
        / ".node"
        / "node_modules"
        / ".bin"
        / ("appium.cmd" if platform.system() == "Windows" else "appium")
    )
    if local.exists():
        return str(local)
    return shutil.which("appium")


def appium_env():
    """Copy the process environment and select the tool-local Appium driver home if present."""
    env = os.environ.copy()
    local_home = TOOL_ROOT / ".appium"
    if local_home.exists():
        env["APPIUM_HOME"] = str(local_home)
    return env


def appium_ready(url):
    """Require the Appium readiness payload, not a generic HTTP 200 page."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/status", timeout=1.5) as response:
            payload = json.load(response)
            return response.status == 200 and isinstance(payload, dict) and isinstance(payload.get("value"), dict) and payload["value"].get("ready") is True
    except Exception:
        return False


def _redact_file(path, env_names, sensitive_values=None):
    """Sanitize known credentials and identifiers in retained local server logs."""
    path = Path(path)
    if not path.exists():
        return
    try:
        values = [os.getenv(name) for name in env_names] + list(sensitive_values or [])
        text = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(redact_values(text, values), encoding="utf-8")
    except OSError:
        pass


def start_appium(cfg, run_root=None):
    """Reuse a responding server or start a local server and return its ownership handle.
    
    An external server is never stopped by this tool. Base-path/TLS/address support
    and startup-failure process cleanup need further validation."""
    appium_cfg = cfg.get("appium", {})
    url = appium_cfg.get("serverUrl", "http://127.0.0.1:4723")
    if appium_ready(url):
        return {"process": None, "external": True, "log": None}

    exe = appium_bin()
    if not exe:
        raise RuntimeError(
            "Appium is not installed. Run scripts/setup-local.sh or scripts/setup-local.ps1."
        )

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise RuntimeError(f"Unsupported Appium serverUrl: {url}")
    if parsed.scheme != "http":
        raise RuntimeError("Local Appium auto-start requires an HTTP URL; configure TLS externally")
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError(
            "Configured Appium server is not reachable. The tool only auto-starts a local server."
        )

    log_base = Path(run_root) if run_root else (TOOL_ROOT / "runs")
    private_dir(log_base)
    log = log_base / "appium.log"
    log_handle = log.open("w", encoding="utf-8")
    try:
        if os.name != "nt":
            os.chmod(log, 0o600)
    except Exception:
        pass

    log_level = str(appium_cfg.get("logLevel", "error"))
    try:
        proc = subprocess.Popen(
            [
                exe,
                "--address",
                host,
                "--base-path",
                parsed.path.rstrip("/") or "/",
                "--port",
                str(port),
                "--log-level",
                log_level,
            ],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=appium_env(),
        )
    finally:
        log_handle.close()

    deadline = time.time() + int(appium_cfg.get("startupTimeoutSeconds", 30))
    while time.time() < deadline:
        if appium_ready(url):
            return {"process": proc, "external": False, "log": str(log)}
        if proc.poll() is not None:
            break
        time.sleep(0.5)

    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        proc.kill()
        proc.wait(timeout=8)
    _redact_file(log, appium_cfg.get("sensitiveEnvNames", []), cfg.get("_sensitiveValues"))
    raise RuntimeError(f"Appium did not start. See redacted log: {log}")


def stop_appium(handle, cfg):
    """Stop only an owned Appium process, redact its log, and remove the log unless retained."""
    if not handle:
        return
    proc = handle.get("process")
    if proc is not None:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=8)
            except Exception:
                pass

    log = handle.get("log")
    if log:
        appium_cfg = cfg.get("appium", {})
        _redact_file(log, appium_cfg.get("sensitiveEnvNames", []), cfg.get("_sensitiveValues"))
        if not bool(appium_cfg.get("saveServerLog", False)):
            try:
                Path(log).unlink()
            except Exception:
                pass


def _cleanup_old_runs(cfg):
    """Best-effort removal of old run directories when retentionDays is positive.
    
    Age uses directory mtime; zero disables cleanup. This deletes local artifacts,
    so use a tool-owned runs directory and dedicated test data."""
    days = int((cfg or {}).get("artifactPrivacy", {}).get("retentionDays", 0) or 0)
    if days <= 0:
        return
    runs = TOOL_ROOT / "runs"
    if not runs.exists():
        return
    cutoff = time.time() - (days * 86400)
    for child in runs.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child)
        except Exception:
            # Retention is best effort and must never break a test run.
            pass


def _new_run_root(suffix="", cfg=None):
    """Create a private run directory named by local time, microseconds, token, and mode suffix."""
    _cleanup_old_runs(cfg)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    token = uuid.uuid4().hex[:8]
    name = f"{stamp}-{token}{suffix}"
    return private_dir((TOOL_ROOT / "runs" / name).resolve())


def _pid_alive(pid):
    """Conservatively check legacy lock owners without terminating Windows processes."""
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return ctypes.get_last_error() != 87  # Access denied is not proof of absence.
            try:
                code = wintypes.DWORD()
                return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
            finally:
                kernel.CloseHandle(handle)
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError, OverflowError):
        return False


def _acquire_run_lock():
    """Acquire a non-inherited kernel lock; empty/dead new-owner files are reusable."""
    lock = (TOOL_ROOT / ".osdiff-run.lock").resolve()
    if str(lock) in _RUN_LOCK_HANDLES:
        raise RuntimeError("Another osdiff run is active")
    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        try:
            _file_lock(fd)
            acquired = True
        except OSError as exc:
            raise RuntimeError("Another osdiff run is active") from exc
        raw = os.read(fd, 512).decode("utf-8", errors="replace").strip()
        fields = raw.split("|")
        # Older releases used only exclusive creation. Respect a live legacy owner.
        if len(fields) == 2 and fields[0].isdigit() and _pid_alive(fields[0]):
            raise RuntimeError("A legacy osdiff run is active")
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}|{time.time()}|kernel-v1".encode("utf-8"))
        os.fsync(fd)
        _RUN_LOCK_HANDLES[str(lock)] = fd
        return lock
    except Exception:
        if acquired:
            _file_lock(fd, unlock=True)
        os.close(fd)
        raise


def _release_run_lock(lock):
    """Release only our descriptor; keep the inode so contenders cannot split ownership."""
    if lock is None:
        return
    fd = _RUN_LOCK_HANDLES.pop(str(Path(lock).resolve()), None)
    if fd is None:
        return
    try:
        os.ftruncate(fd, 0)
    finally:
        try:
            _file_lock(fd, unlock=True)
        finally:
            os.close(fd)

def scenario_files(args):
    """Resolve explicit scenario arguments from cwd, or enumerate tool-local JSON examples."""
    if args.scenario:
        return [str(Path(s).resolve()) for s in args.scenario]
    return [str(p.resolve()) for p in sorted((TOOL_ROOT / "scenarios").glob("*.json"))]


def runtime_for(cfg, platform_name, target, info):
    """Build virtual-target Appium/reset settings with config-relative app paths and privacy inputs."""
    platform_cfg = cfg[platform_name]
    out = {
        "udid": info["udid"],
        "appPath": resolve_path(cfg, platform_cfg["appPath"]),
        "deviceName": (
            platform_cfg.get("deviceType", "iPhone")
            if platform_name == "ios"
            else target
        ),
        "checkpointSettleSeconds": cfg.get("comparison", {}).get(
            "checkpointSettleSeconds", 0.25
        ),
        "noReset": bool(platform_cfg.get("noReset", False)),
        "sensitiveEnvNames": cfg.get("appium", {}).get(
            "sensitiveEnvNames", ["TEST_USER_EMAIL", "TEST_USER_PASSWORD"]
        ),
        "sensitiveRegions": cfg.get("artifactPrivacy", {}).get("sensitiveRegions", {}),
        "resetStrategy": platform_cfg.get(
            "autoResetStrategy",
            "android_clear_data" if platform_name == "android" else "ios_simulator_reinstall",
        ),
    }
    if platform_name == "android":
        out.update(
            appPackage=platform_cfg.get("appPackage"),
            appActivity=platform_cfg.get("appActivity"),
            autoGrantPermissions=bool(platform_cfg.get("autoGrantPermissions", False)),
        )
    else:
        out.update(bundleId=platform_cfg.get("bundleId"))
    return out


def ensure_app(path, platform_name):
    """Check binary existence and expected extension; app version/signature is not inspected."""
    app = Path(path)
    if not app.exists():
        raise RuntimeError(f"{platform_name} app not found: {app}")
    if platform_name == "ios" and app.suffix != ".app":
        raise RuntimeError(
            "This tool uses iOS Simulator and expects a simulator .app bundle, not an .ipa."
        )
    if platform_name == "android" and app.suffix.lower() != ".apk":
        raise RuntimeError("This tool expects an Android .apk.")


def _summaries_have_failures(summary):
    """Identify non-passed scenario statuses; nested assertions/actions need separate validation."""
    return any(entry.get("status") != "passed" for entry in summary)


def run_one_platform(cfg, platform_name, run_root, scenarios):
    """Run baseline then candidate virtual targets, always attempting to stop each owned device."""
    from osdiff.runner import run_target
    server = cfg["appium"].get("serverUrl", "http://127.0.0.1:4723")
    platform_cfg = cfg[platform_name]
    ensure_app(resolve_path(cfg, platform_cfg["appPath"]), platform_name)
    execution = {"baseline": [], "candidate": []}

    if platform_name == "android":
        baseline = platform_cfg["baseline"]
        candidate = platform_cfg["candidate"]
        for target in (baseline, candidate):
            if "REPLACE_WITH_" in str(target.get("apiLevel", "")):
                raise RuntimeError(
                    "Edit Android baseline/candidate apiLevel values in config/local-config.json."
                )

        baseline_info = None
        try:
            print(f"[android] Starting baseline API {baseline['apiLevel']} ...")
            baseline_info = devices.prepare_android(
                baseline["apiLevel"],
                baseline["avdName"],
                platform_cfg.get("imageTag", "google_apis"),
                platform_cfg.get("abi", "x86_64"),
                platform_cfg.get("deviceProfile", "pixel"),
                recreate=bool(platform_cfg.get("recreateDeviceEachRun", True)),
                log_root=run_root / "android" / "emulator-logs",
            )
            execution["baseline"] = run_target(
                server,
                runtime_for(cfg, "android", "baseline", baseline_info),
                "android",
                scenarios,
                run_root / "android" / "baseline",
            )
            if _summaries_have_failures(execution["baseline"]):
                print("[android] Baseline failed; final comparison will be marked INVALID.")
        finally:
            devices.stop_android(baseline_info)

        candidate_info = None
        try:
            print(f"[android] Starting candidate API {candidate['apiLevel']} ...")
            candidate_info = devices.prepare_android(
                candidate["apiLevel"],
                candidate["avdName"],
                platform_cfg.get("imageTag", "google_apis"),
                platform_cfg.get("abi", "x86_64"),
                platform_cfg.get("deviceProfile", "pixel"),
                recreate=bool(platform_cfg.get("recreateDeviceEachRun", True)),
                log_root=run_root / "android" / "emulator-logs",
            )
            execution["candidate"] = run_target(
                server,
                runtime_for(cfg, "android", "candidate", candidate_info),
                "android",
                scenarios,
                run_root / "android" / "candidate",
            )
            if _summaries_have_failures(execution["candidate"]):
                print("[android] Candidate failed; final comparison will record the failure.")
        finally:
            devices.stop_android(candidate_info)

    else:
        if platform.system() != "Darwin":
            raise RuntimeError("iOS local regression testing requires macOS with Xcode.")
        baseline = platform_cfg["baseline"]
        candidate = platform_cfg["candidate"]
        for target in (baseline, candidate):
            if "REPLACE_WITH_" in str(target.get("runtimeVersion", "")):
                raise RuntimeError(
                    "Edit iOS baseline/candidate runtimeVersion values in config/local-config.json."
                )

        baseline_info = None
        try:
            print(f"[ios] Starting baseline iOS {baseline['runtimeVersion']} ...")
            baseline_info = devices.prepare_ios(
                baseline["runtimeVersion"],
                platform_cfg["deviceType"],
                baseline["simulatorName"],
                recreate=bool(platform_cfg.get("recreateDeviceEachRun", True)),
            )
            execution["baseline"] = run_target(
                server,
                runtime_for(cfg, "ios", "baseline", baseline_info),
                "ios",
                scenarios,
                run_root / "ios" / "baseline",
            )
            if _summaries_have_failures(execution["baseline"]):
                print("[ios] Baseline failed; final comparison will be marked INVALID.")
        finally:
            devices.stop_ios(baseline_info)

        candidate_info = None
        try:
            print(f"[ios] Starting candidate iOS {candidate['runtimeVersion']} ...")
            candidate_info = devices.prepare_ios(
                candidate["runtimeVersion"],
                platform_cfg["deviceType"],
                candidate["simulatorName"],
                recreate=bool(platform_cfg.get("recreateDeviceEachRun", True)),
            )
            execution["candidate"] = run_target(
                server,
                runtime_for(cfg, "ios", "candidate", candidate_info),
                "ios",
                scenarios,
                run_root / "ios" / "candidate",
            )
            if _summaries_have_failures(execution["candidate"]):
                print("[ios] Candidate failed; final comparison will record the failure.")
        finally:
            devices.stop_ios(candidate_info)

    return execution


def _apply_auto_overrides(cfg, args, platform_name):
    """Apply explicit binary/OS/device overrides in-place; --app clears inferred app identity."""
    platform_cfg = cfg[platform_name]
    if getattr(args, "app", None):
        platform_cfg["appPath"] = str(Path(args.app).expanduser().resolve())
        # When a binary is supplied directly, allow Appium to infer identity unless
        # the operator explicitly provides it.
        if platform_name == "android":
            platform_cfg["appPackage"] = getattr(args, "app_package", None)
            platform_cfg["appActivity"] = getattr(args, "app_activity", None)
        else:
            platform_cfg["bundleId"] = getattr(args, "bundle_id", None)

    if getattr(args, "baseline_os", None):
        if platform_name == "android":
            platform_cfg["baseline"]["apiLevel"] = str(args.baseline_os)
        else:
            platform_cfg["baseline"]["runtimeVersion"] = str(args.baseline_os)
    if getattr(args, "candidate_os", None):
        if platform_name == "android":
            platform_cfg["candidate"]["apiLevel"] = str(args.candidate_os)
        else:
            platform_cfg["candidate"]["runtimeVersion"] = str(args.candidate_os)

    if platform_name == "ios" and getattr(args, "device_type", None):
        platform_cfg["deviceType"] = args.device_type

    if getattr(args, "unsafe_full_crawl", False):
        cfg.setdefault("crawler", {})["safeMode"] = False


def auto_crawl_one_platform(cfg, platform_name, run_root):
    """Provision two virtual targets, discover baseline paths, replay candidate, and summarize coverage."""
    from osdiff.crawler import crawl_baseline, replay_candidate_graph, coverage_summary

    server = cfg["appium"].get("serverUrl", "http://127.0.0.1:4723")
    platform_cfg = cfg[platform_name]
    crawler_cfg = dict(cfg.get("crawler", {}))
    crawler_cfg["sensitiveValues"] = [
        os.getenv(name) for name in cfg.get("appium", {}).get("sensitiveEnvNames", [])
        if os.getenv(name)
    ]
    crawler_cfg["sensitiveRegions"] = cfg.get("artifactPrivacy", {}).get("sensitiveRegions", {})
    ensure_app(resolve_path(cfg, platform_cfg["appPath"]), platform_name)

    if platform_name == "android":
        baseline = platform_cfg["baseline"]
        candidate = platform_cfg["candidate"]
        for target in (baseline, candidate):
            if "REPLACE_WITH_" in str(target.get("apiLevel", "")):
                raise RuntimeError(
                    "Provide Android baseline/candidate API levels with --baseline-os/--candidate-os "
                    "or edit config/local-config.json."
                )

        baseline_info = None
        try:
            print(f"[android:auto] Discovering screens on baseline API {baseline['apiLevel']} ...")
            baseline_info = devices.prepare_android(
                baseline["apiLevel"],
                baseline["avdName"],
                platform_cfg.get("imageTag", "google_apis"),
                platform_cfg.get("abi", "x86_64"),
                platform_cfg.get("deviceProfile", "pixel"),
                recreate=bool(platform_cfg.get("recreateDeviceEachRun", True)),
                log_root=run_root / "android" / "emulator-logs",
            )
            baseline_graph = crawl_baseline(
                server,
                runtime_for(cfg, "android", "baseline", baseline_info),
                "android",
                run_root / "android" / "baseline",
                crawler_cfg,
            )
        finally:
            devices.stop_android(baseline_info)

        candidate_info = None
        try:
            print(
                f"[android:auto] Replaying {baseline_graph.get('discoveredScreens',0)} "
                f"discovered screens on candidate API {candidate['apiLevel']} ..."
            )
            candidate_info = devices.prepare_android(
                candidate["apiLevel"],
                candidate["avdName"],
                platform_cfg.get("imageTag", "google_apis"),
                platform_cfg.get("abi", "x86_64"),
                platform_cfg.get("deviceProfile", "pixel"),
                recreate=bool(platform_cfg.get("recreateDeviceEachRun", True)),
                log_root=run_root / "android" / "emulator-logs",
            )
            candidate_replay = replay_candidate_graph(
                server,
                runtime_for(cfg, "android", "candidate", candidate_info),
                "android",
                baseline_graph,
                run_root / "android" / "candidate",
                crawler_cfg,
            )
        finally:
            devices.stop_android(candidate_info)

    else:
        if platform.system() != "Darwin":
            raise RuntimeError("iOS automatic crawling requires macOS with Xcode.")
        baseline = platform_cfg["baseline"]
        candidate = platform_cfg["candidate"]
        for target in (baseline, candidate):
            if "REPLACE_WITH_" in str(target.get("runtimeVersion", "")):
                raise RuntimeError(
                    "Provide iOS baseline/candidate runtime versions with --baseline-os/--candidate-os "
                    "or edit config/local-config.json."
                )

        baseline_info = None
        try:
            print(f"[ios:auto] Discovering screens on baseline iOS {baseline['runtimeVersion']} ...")
            baseline_info = devices.prepare_ios(
                baseline["runtimeVersion"],
                platform_cfg["deviceType"],
                baseline["simulatorName"],
                recreate=bool(platform_cfg.get("recreateDeviceEachRun", True)),
            )
            baseline_graph = crawl_baseline(
                server,
                runtime_for(cfg, "ios", "baseline", baseline_info),
                "ios",
                run_root / "ios" / "baseline",
                crawler_cfg,
            )
        finally:
            devices.stop_ios(baseline_info)

        candidate_info = None
        try:
            print(
                f"[ios:auto] Replaying {baseline_graph.get('discoveredScreens',0)} "
                f"discovered screens on candidate iOS {candidate['runtimeVersion']} ..."
            )
            candidate_info = devices.prepare_ios(
                candidate["runtimeVersion"],
                platform_cfg["deviceType"],
                candidate["simulatorName"],
                recreate=bool(platform_cfg.get("recreateDeviceEachRun", True)),
            )
            candidate_replay = replay_candidate_graph(
                server,
                runtime_for(cfg, "ios", "candidate", candidate_info),
                "ios",
                baseline_graph,
                run_root / "ios" / "candidate",
                crawler_cfg,
            )
        finally:
            devices.stop_ios(candidate_info)

    return coverage_summary(baseline_graph, candidate_replay)


def auto_run_cmd(args):
    """Orchestrate virtual automatic discovery, artifacts, comparison, and the 0/2/3 result codes."""
    cfg = load_config(args.config)
    platforms = ["android", "ios"] if args.platform == "all" else [args.platform]
    if args.platform == "all" and getattr(args, "app", None):
        raise RuntimeError(
            "--app can only be used with one platform at a time. For --platform all, "
            "set android.appPath and ios.appPath in the config file."
        )

    for platform_name in platforms:
        _apply_auto_overrides(cfg, args, platform_name)

    run_root = _new_run_root("-auto", cfg)
    report_root = private_dir(run_root / "report")

    appium_handle = start_appium(cfg, run_root)
    try:
        executed = []
        coverage = {}
        for platform_name in platforms:
            if not cfg.get(platform_name, {}).get("enabled", True):
                print(f"[{platform_name}] disabled in configuration; skipping.")
                continue
            if platform_name == "ios" and platform.system() != "Darwin":
                if args.platform == "all":
                    print("[ios] skipped: iOS Simulator requires macOS.")
                    continue
                raise RuntimeError("iOS Simulator testing requires macOS with Xcode.")
            coverage[platform_name] = auto_crawl_one_platform(
                cfg, platform_name, run_root
            )
            executed.append(platform_name)

        if not executed:
            raise RuntimeError("No platform was executed.")

        results = []
        for platform_name in executed:
            results += compare_platform(
                run_root, platform_name, cfg["comparison"], report_root
            )

        summary = write_report(
            report_root,
            results,
            cfg.get("projectName", "Mobile App"),
            coverage=coverage,
        )
        write_json(report_root / "coverage.json", coverage)

        print("\nAutomatic crawl completed.")
        print(json.dumps(summary, indent=2))
        for platform_name, item in coverage.items():
            print(
                f"[{platform_name}] discovered={item['discoveredBaselineScreens']} "
                f"reproduced={item['candidateScreensReproduced']} "
                f"coverage={item['coverageStatus']} "
                f"blockedUnsafe={item['blockedUnsafeActions']} "
                f"blockedInputs={item['blockedInputs']}"
            )
        print(f"Report: {report_root / 'index.html'}")
        if args.open:
            webbrowser.open((report_root / "index.html").as_uri())

        incomplete_coverage = any(
            item.get("coverageStatus") != "COMPLETE_WITHIN_POLICY"
            for item in coverage.values()
        )
        if summary["invalid"] or incomplete_coverage:
            return 3
        if summary["highRisk"]:
            return 2
        return 0
    finally:
        stop_appium(appium_handle, cfg)

def _version_tuple(text):
    """Extract a three-part numeric version for prerequisite checks, or return None."""
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not match:
        return None
    return tuple(int(value or 0) for value in match.groups())


def _node_supported(version):
    """Apply the Node engine ranges used by this tool's setup scripts."""
    if not version:
        return False
    major, minor, _ = version
    return (major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major >= 24


def _run_version(cmd, args):
    """Run a bounded version command and return its code and stdout/stderr detail."""
    try:
        result = subprocess.run([cmd, *args], text=True, capture_output=True, timeout=10)
        return result.returncode, (result.stdout or result.stderr).strip()
    except Exception as exc:
        return 1, str(exc)


def _appium_doctor(driver_name):
    """Run the selected driver's prerequisite checks in the tool-local Appium environment."""
    exe = appium_bin()
    if not exe:
        return False, "Appium not found"
    try:
        result = subprocess.run(
            [exe, "driver", "doctor", driver_name, "--json"],
            text=True,
            capture_output=True,
            timeout=90,
            env=appium_env(),
        )
        detail = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, detail[-1200:]
    except Exception as exc:
        return False, str(exc)


def doctor(args):
    """Report mode/platform prerequisites; passing checks is not device or signing validation."""
    cfg = load_config(args.config)
    rows = []

    def add(name, ok, detail):
        rows.append((name, bool(ok), detail))

    mode = getattr(args, "mode", "all")
    requested_platform = getattr(args, "platform", "all")
    wants_virtual = mode in ("virtual", "all")
    wants_market = mode in ("market", "all")
    wants_android = requested_platform in ("android", "all") and bool(cfg.get("android", {}).get("enabled", True))
    wants_ios = requested_platform in ("ios", "all") and bool(cfg.get("ios", {}).get("enabled", True))

    add("Python >= 3.10", sys.version_info >= (3, 10), sys.version.split()[0])
    if command_exists("node"):
        rc, value = _run_version("node", ["--version"])
        node_version = _version_tuple(value)
        add("Node.js supported", rc == 0 and _node_supported(node_version), value)
    else:
        add("Node.js supported", False, "not found")
    if command_exists("npm"):
        rc, value = _run_version("npm", ["--version"])
        npm_version = _version_tuple(value)
        add("npm >= 10", rc == 0 and npm_version and npm_version[0] >= 10, value)
    else:
        add("npm >= 10", False, "not found")
    add("Appium", bool(appium_bin()), appium_bin() or "not found")

    if wants_android:
        adb = devices.adb_path()
        add("adb", bool(adb), adb or "not found")
        java_home = os.getenv("JAVA_HOME")
        add("JAVA_HOME", bool(java_home), java_home or "not set")
        add("Java", command_exists("java"), shutil.which("java") or "not found")
        ok, detail = _appium_doctor("uiautomator2")
        add("UiAutomator2 doctor", ok, detail or "no output")
        if wants_virtual:
            add(
                "ANDROID SDK root",
                bool(devices.android_sdk_root()),
                devices.android_sdk_root() or "ANDROID_SDK_ROOT / ANDROID_HOME not set",
            )
            for name, fn in [
                ("emulator", devices.emulator_path),
                ("sdkmanager", lambda: devices.sdk_tool("sdkmanager")),
                ("avdmanager", lambda: devices.sdk_tool("avdmanager")),
            ]:
                value = fn()
                add(name, bool(value), value or "not found")

    if wants_ios:
        if platform.system() != "Darwin":
            add("macOS for iOS", False, "iOS testing requires macOS")
        else:
            add("Xcode/xcrun", command_exists("xcrun"), shutil.which("xcrun") or "not found")
            try:
                result = subprocess.run(["xcodebuild", "-version"], text=True, capture_output=True, timeout=20)
                add("Xcode active", result.returncode == 0, (result.stdout or result.stderr).strip())
            except Exception as exc:
                add("Xcode active", False, str(exc))
            ok, detail = _appium_doctor("xcuitest")
            add("XCUITest doctor", ok, detail or "no output")
            if wants_market:
                add("Real-device WDA signing", True, "verify provisioning/signing during first market-run session")

    print(f"\nOS Differential Regression Tester â€” doctor ({mode}/{requested_platform})\n")
    for name, ok, detail in rows:
        compact = " ".join(str(detail).split())
        if len(compact) > 180:
            compact = compact[:177] + "..."
        print(f"{'PASS' if ok else 'FAIL':4}  {name:24}  {compact}")
    return 1 if any(not row[1] for row in rows) else 0


def list_targets(args):
    """Print configured virtual-target availability; emulator listing currently lacks a timeout."""
    print("\nAndroid AVDs")
    emulator = devices.emulator_path()
    if emulator:
        result = subprocess.run([emulator, "-list-avds"], text=True, capture_output=True, timeout=30)
        print(result.stdout.strip() or "(none)")
    else:
        print("(emulator tool not found)")

    if platform.system() == "Darwin":
        print("\niOS Simulator runtimes")
        try:
            for runtime in devices.ios_runtimes():
                print(
                    f"- {runtime.get('name')}  version={runtime.get('version')}  "
                    f"id={runtime.get('identifier')}"
                )
        except Exception as exc:
            print(f"(unable to read: {exc})")


def open_report(args):
    """Resolve a report file/directory and open its existing local HTML page."""
    path = Path(args.report).resolve()
    if path.is_dir():
        path = path / "index.html"
    if not path.exists():
        raise SystemExit(f"Report not found: {path}")
    webbrowser.open(path.as_uri())
    print(path)


def run_cmd(args):
    """Run explicit scenarios on enabled virtual platforms and return comparison exit status."""
    cfg = load_config(args.config)
    scenarios = scenario_files(args)
    if not scenarios:
        raise RuntimeError("No scenario JSON files found.")
    missing_scenarios = [path for path in scenarios if not Path(path).exists()]
    if missing_scenarios:
        raise RuntimeError("Scenario file(s) not found: " + ", ".join(missing_scenarios))

    run_root = _new_run_root(cfg=cfg)
    report_root = private_dir(run_root / "report")

    appium_handle = start_appium(cfg, run_root)
    try:
        platforms = ["android", "ios"] if args.platform == "all" else [args.platform]
        executed = []
        for platform_name in platforms:
            if not cfg.get(platform_name, {}).get("enabled", True):
                print(f"[{platform_name}] disabled in configuration; skipping.")
                continue
            if platform_name == "ios" and platform.system() != "Darwin":
                if args.platform == "all":
                    print("[ios] skipped: iOS Simulator requires macOS.")
                    continue
                raise RuntimeError("iOS Simulator testing requires macOS with Xcode.")
            run_one_platform(cfg, platform_name, run_root, scenarios)
            executed.append(platform_name)

        if not executed:
            raise RuntimeError("No platform was executed.")

        results = []
        for platform_name in executed:
            results += compare_platform(
                run_root, platform_name, cfg["comparison"], report_root
            )
        summary = write_report(
            report_root, results, cfg.get("projectName", "Mobile App")
        )
        print("\nCompleted.")
        print(json.dumps(summary, indent=2))
        print(f"Report: {report_root / 'index.html'}")
        if args.open:
            webbrowser.open((report_root / "index.html").as_uri())

        # Exit code contract: 0=pass/review only, 2=OS regression, 3=invalid/incomplete.
        if summary["invalid"]:
            return 3
        if summary["highRisk"]:
            return 2
        return 0
    finally:
        stop_appium(appium_handle, cfg)



def list_real_devices_cmd(args):
    """List authorized Android serials and Xcode-listed iOS devices without running the app."""
    from osdiff import market

    print("\nAndroid physical devices")
    if devices.adb_path():
        devices_found = []
        for item in market.list_android_devices():
            serial = item.get("serial", "")
            if serial.startswith("emulator-"):
                continue
            devices_found.append(item)
            print(
                f"- serial={serial} model={item.get('model','?')} "
                f"device={item.get('device','?')} product={item.get('product','?')}"
            )
        if not devices_found:
            print("(none)")
    else:
        print("(adb not found)")

    print("\niOS physical devices")
    if platform.system() != "Darwin":
        print("(requires macOS + Xcode)")
        return 0
    try:
        proc = subprocess.run(
            ["xcrun", "xctrace", "list", "devices"],
            text=True,
            capture_output=True,
            timeout=30,
        )
        output = proc.stdout or proc.stderr
        physical = []
        in_simulators = False
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("== Simulators"):
                in_simulators = True
                continue
            if stripped.startswith("== Devices"):
                in_simulators = False
                continue
            if in_simulators or not stripped:
                continue
            if re.search(r"\([0-9A-Fa-f-]{20,}\)\s*$", stripped) and (
                "iPhone" in stripped or "iPad" in stripped or "iPod" in stripped
            ):
                physical.append(stripped)
        for line in physical:
            print(f"- {line}")
        if not physical:
            print("(none detected; confirm trust/Developer Mode in Xcode)")
    except Exception as exc:
        print(f"(unable to list: {exc})")
    return 0


def _market_invalid_result(platform_name, validation):
    """Create the synthetic INVALID report row for a failed provenance/environment gate."""
    reasons = list(validation.get("errors") or [])
    if not reasons:
        reasons = ["market_provenance_validation_failed"]
    return {
        "comparisonStatus": "INVALID",
        "riskScore": 100,
        "severity": "Critical",
        "platform": platform_name,
        "scenario": "market_provenance",
        "checkpoint": "__market_provenance__",
        "reasons": reasons,
        "behaviorRegressions": [],
        "visual": {},
        "hierarchyChangeRatio": 0.0,
        "images": {},
    }


def market_run_cmd(args):
    """Verify preinstalled builds, crawl baseline, replay candidate, and write market evidence.
    
    No app binary is supplied by the normal market runtime. Preflight identity
    checks and policy-derived coverage still have the gaps in the baseline assessment."""
    from osdiff import market
    from osdiff.crawler import crawl_baseline, replay_candidate_graph, coverage_summary

    cfg = load_config(args.config)
    platform_name = args.platform
    cfg["_sensitiveValues"] = [args.baseline_device, args.candidate_device]
    policy = cfg.get("marketMode", {})
    crawler_cfg = dict(cfg.get("crawler", {}))
    crawler_cfg["sensitiveValues"] = [
        os.getenv(name) for name in cfg.get("appium", {}).get("sensitiveEnvNames", [])
        if os.getenv(name)
    ]
    crawler_cfg["sensitiveRegions"] = cfg.get("artifactPrivacy", {}).get("sensitiveRegions", {})
    if args.unsafe_full_crawl:
        crawler_cfg["safeMode"] = False

    run_root = _new_run_root("-market-real", cfg)
    report_root = private_dir(run_root / "report")

    appium_handle = start_appium(cfg, run_root)
    try:
        server = cfg["appium"].get("serverUrl", "http://127.0.0.1:4723")
        if platform_name == "android":
            allowed = args.allow_android_installer or policy.get(
                "androidAllowedInstallers", ["com.android.vending"]
            )
            print("[market] Verifying baseline Android physical device and Play-installed app ...")
            baseline = market.probe_android_market_device(
                args.baseline_device,
                args.app_id,
                allowed_installers=allowed,
                app_activity=args.app_activity,
            )
            print("[market] Verifying candidate Android physical device and Play-installed app ...")
            candidate = market.probe_android_market_device(
                args.candidate_device,
                args.app_id,
                allowed_installers=allowed,
                app_activity=args.app_activity,
            )
        else:
            if platform.system() != "Darwin":
                raise RuntimeError("iOS market-run requires macOS with Xcode.")
            requires_attestation = bool(policy.get("iosRequireAppStoreAttestation", True))
            if requires_attestation and not args.ios_app_store_confirmed:
                raise RuntimeError(
                    "iOS market-run requires --ios-app-store-confirmed. XCUITest can verify "
                    "the preinstalled bundle/version/build, but public automation metadata does "
                    "not reliably prove App Store origin. Confirm both devices were installed "
                    "from the Apple App Store before proceeding."
                )
            print("[market] Inspecting baseline iOS physical device / preinstalled App Store app ...")
            baseline = market.probe_ios_market_device(
                server, args.baseline_device, args.app_id,
                app_store_confirmed=args.ios_app_store_confirmed,
            )
            print("[market] Inspecting candidate iOS physical device / preinstalled App Store app ...")
            candidate = market.probe_ios_market_device(
                server, args.candidate_device, args.app_id,
                app_store_confirmed=args.ios_app_store_confirmed,
            )

        require_same_model = bool(
            args.require_same_model or policy.get("requireSameHardwareModel", False)
        )
        validation = market.validate_market_pair(
            baseline,
            candidate,
            require_same_model=require_same_model,
            require_matching_environment=bool(policy.get("requireMatchingEnvironment", True)),
        )
        provenance = market.write_provenance(
            report_root / "device-provenance.json", baseline, candidate, validation
        )

        print("\nMarket provenance gate")
        print(f"Baseline:  {baseline.get('deviceName')} | OS {baseline.get('osVersion')} | "
              f"app {baseline.get('appVersion')} build {baseline.get('appBuild')}")
        print(f"Candidate: {candidate.get('deviceName')} | OS {candidate.get('osVersion')} | "
              f"app {candidate.get('appVersion')} build {candidate.get('appBuild')}")
        print(f"Exact app version/build match: {validation.get('sameAppVersionAndBuild')}")
        print(f"Market provenance valid: {validation.get('valid')}")
        for warning in validation.get("warnings", []):
            print(f"WARNING: {warning}")

        if not validation.get("valid"):
            result = _market_invalid_result(platform_name, validation)
            summary = write_report(
                report_root,
                [result],
                cfg.get("projectName", "Mobile App"),
                provenance=provenance,
            )
            print("\nINVALID: market provenance gate failed.")
            print(json.dumps(summary, indent=2))
            print(f"Report: {report_root / 'index.html'}")
            if args.open:
                webbrowser.open((report_root / "index.html").as_uri())
            return 3

        print("\n[market] Baseline automatic discovery on physical device ...")
        baseline_graph = crawl_baseline(
            server,
            market.market_runtime(
                baseline,
                platform_name,
                reset_strategy=policy.get("androidResetStrategy") if platform_name == "android" else policy.get("iosResetStrategy"),
                reset_command=policy.get("iosResetCommand") if platform_name == "ios" else None,
            ),
            platform_name,
            run_root / platform_name / "baseline",
            crawler_cfg,
        )
        print(
            f"[market] Replaying {baseline_graph.get('discoveredScreens', 0)} baseline screens "
            "on candidate physical device ..."
        )
        candidate_replay = replay_candidate_graph(
            server,
            market.market_runtime(
                candidate,
                platform_name,
                reset_strategy=policy.get("androidResetStrategy") if platform_name == "android" else policy.get("iosResetStrategy"),
                reset_command=policy.get("iosResetCommand") if platform_name == "ios" else None,
            ),
            platform_name,
            baseline_graph,
            run_root / platform_name / "candidate",
            crawler_cfg,
        )
        coverage_item = coverage_summary(baseline_graph, candidate_replay)
        coverage = {platform_name: coverage_item}
        write_json(report_root / "coverage.json", coverage)

        # Detect store auto-updates or target identity changes during the run.
        try:
            if platform_name == "android":
                final_b = market.probe_android_market_device(args.baseline_device, args.app_id, allowed_installers=allowed, app_activity=args.app_activity)
                final_c = market.probe_android_market_device(args.candidate_device, args.app_id, allowed_installers=allowed, app_activity=args.app_activity)
            else:
                final_b = market.probe_ios_market_device(server, args.baseline_device, args.app_id, app_store_confirmed=args.ios_app_store_confirmed)
                final_c = market.probe_ios_market_device(server, args.candidate_device, args.app_id, app_store_confirmed=args.ios_app_store_confirmed)
            final_validation = market.validate_market_pair_after_run(
                baseline, candidate, final_b, final_c, require_same_model=require_same_model,
                require_matching_environment=bool(policy.get("requireMatchingEnvironment", True)))
            provenance = market.write_provenance(report_root / "device-provenance.json", baseline, candidate, final_validation)
        except Exception:
            validation = dict(validation, valid=False, errors=[*validation.get("errors", []), "post_run_identity_unavailable"], postRunIdentityVerified=False)
            provenance = market.write_provenance(report_root / "device-provenance.json", baseline, candidate, validation)
        results = compare_platform(
            run_root, platform_name, cfg["comparison"], report_root
        )
        summary = write_report(
            report_root,
            results,
            cfg.get("projectName", "Mobile App"),
            coverage=coverage,
            provenance=provenance,
        )

        print("\nReal-device market comparison completed.")
        print(json.dumps(summary, indent=2))
        print(
            f"Coverage: {coverage_item.get('coverageStatus')} | "
            f"baseline discovered={coverage_item.get('discoveredBaselineScreens')} | "
            f"candidate reproduced={coverage_item.get('candidateScreensReproduced')}"
        )
        print(f"Report: {report_root / 'index.html'}")
        if args.open:
            webbrowser.open((report_root / "index.html").as_uri())

        if summary["invalid"]:
            return 3
        if summary["highRisk"]:
            return 2
        return 0
    finally:
        stop_appium(appium_handle, cfg)

def main():
    """Parse CLI arguments and translate execution errors/cancellation into process exit codes.
    
    Known lifecycle defect: the acquired run lock has no cleanup finally block.
    Documentation additions do not repair this behavior."""
    parser = argparse.ArgumentParser(
        prog="osdiff",
        description="Local old-OS vs new-OS mobile differential regression tester",
    )
    parser.add_argument(
        "--config", default=str(TOOL_ROOT / "config" / "local-config.json")
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    doctor_parser = sub.add_parser("doctor", help="Check local prerequisites")
    doctor_parser.add_argument("--mode", choices=["virtual", "market", "all"], default="all")
    doctor_parser.add_argument("--platform", choices=["android", "ios", "all"], default="all")
    doctor_parser.set_defaults(func=doctor)
    list_parser = sub.add_parser("list-targets", help="List installed AVDs and iOS runtimes")
    list_parser.set_defaults(func=list_targets)
    run_parser = sub.add_parser("run", help="Run baseline and candidate OS comparison")
    run_parser.add_argument(
        "--platform", choices=["android", "ios", "all"], default="all"
    )
    run_parser.add_argument(
        "--scenario",
        action="append",
        help="Scenario JSON file. Repeat for multiple. Default: all scenarios/*.json",
    )
    run_parser.add_argument("--open", action="store_true", help="Open HTML report when finished")
    run_parser.set_defaults(func=run_cmd)
    auto_parser = sub.add_parser(
        "auto-run",
        help="Automatically discover baseline screens and compare them on the candidate OS",
    )
    auto_parser.add_argument(
        "--platform", choices=["android", "ios", "all"], default="all"
    )
    auto_parser.add_argument(
        "--app",
        help="Test app binary: Android APK or iOS Simulator .app. Overrides config appPath.",
    )
    auto_parser.add_argument(
        "--baseline-os",
        help="Android API level or iOS Simulator runtime version for the baseline OS.",
    )
    auto_parser.add_argument(
        "--candidate-os",
        help="Android API level or iOS Simulator runtime version for the candidate/new OS.",
    )
    auto_parser.add_argument("--app-package", help="Android package ID. Optional when Appium can infer it.")
    auto_parser.add_argument("--app-activity", help="Android launch activity. Optional when Appium can infer it.")
    auto_parser.add_argument("--bundle-id", help="iOS bundle ID. Optional when Appium can infer it.")
    auto_parser.add_argument("--device-type", help="iOS Simulator device type, e.g. 'iPhone 16'.")
    auto_parser.add_argument(
        "--unsafe-full-crawl",
        action="store_true",
        help="Disable destructive-action keyword blocking. Use only with disposable test data.",
    )
    auto_parser.add_argument("--open", action="store_true", help="Open HTML report when finished")
    auto_parser.set_defaults(func=auto_run_cmd)
    real_parser = sub.add_parser(
        "list-real-devices",
        help="List connected physical Android/iOS devices for market-run",
    )
    real_parser.set_defaults(func=list_real_devices_cmd)

    market_parser = sub.add_parser(
        "market-run",
        help="Compare the same preinstalled market app on two physical devices",
    )
    market_parser.add_argument("--platform", choices=["android", "ios"], required=True)
    market_parser.add_argument(
        "--app-id", required=True,
        help="Android package ID or iOS bundle ID of the market-installed app",
    )
    market_parser.add_argument("--baseline-device", required=True, help="ADB serial or iOS UDID for old-OS device")
    market_parser.add_argument("--candidate-device", required=True, help="ADB serial or iOS UDID for new-OS device")
    market_parser.add_argument("--app-activity", help="Android launch activity if automatic resolution fails")
    market_parser.add_argument(
        "--allow-android-installer", action="append",
        help="Allowed Android installer package. Repeat as needed. Default: com.android.vending",
    )
    market_parser.add_argument(
        "--ios-app-store-confirmed", action="store_true",
        help="Attest that the preinstalled app on both iOS devices came from Apple App Store",
    )
    market_parser.add_argument(
        "--require-same-model", action="store_true",
        help="Make different baseline/candidate hardware models an INVALID condition",
    )
    market_parser.add_argument(
        "--unsafe-full-crawl", action="store_true",
        help="Disable destructive-action keyword blocking. Use only with disposable test accounts/data.",
    )
    market_parser.add_argument("--open", action="store_true", help="Open HTML report when finished")
    market_parser.set_defaults(func=market_run_cmd)

    open_parser = sub.add_parser("open-report", help="Open an existing report")
    open_parser.add_argument("report")
    open_parser.set_defaults(func=open_report)
    args = parser.parse_args()
    lock = None
    try:
        if args.cmd in {"run", "auto-run", "market-run"}:
            lock = _acquire_run_lock()
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        secrets = [os.getenv(name) for name in ("TEST_USER_EMAIL", "TEST_USER_PASSWORD")]
        try:
            config = load_config(args.config)
            secrets += [os.getenv(name) for name in config.get("appium", {}).get("sensitiveEnvNames", [])]
            from osdiff.crawler import _sensitive_values
            secrets += _sensitive_values(config.get("crawler", {}))
        except Exception:
            pass
        secrets += [getattr(args, "baseline_device", None), getattr(args, "candidate_device", None)]
        print("\nERROR: " + redact_values(str(exc), secrets), file=sys.stderr)
        return 1
    finally:
        _release_run_lock(lock)


if __name__ == "__main__":
    raise SystemExit(main())
