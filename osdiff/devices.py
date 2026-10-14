"""Provision and stop virtual Android/iOS targets with explicit runtime identity.

These helpers may install SDK images, recreate named AVDs/simulators, wipe virtual
device data, and stop owned processes. Physical market-run uses osdiff.market
instead. Every ADB operation on an owned emulator must include its selected serial.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import time
import uuid
import re

from osdiff.fsutil import private_dir, private_file
from pathlib import Path


def _run(args, check=True, capture=True, env=None, input_text=None, timeout=120):
    """Run a bounded SDK/ADB/simctl command, raising on timeout or checked nonzero exit."""
    try:
        p = subprocess.run(
            args,
            text=True,
            input=input_text,
            capture_output=capture,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(map(str, args))}") from exc
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout or "").strip())
    return (p.stdout or "").strip()


def which(name):
    """Resolve a tool through PATH without executing it."""
    return shutil.which(name)


def android_sdk_root():
    """Prefer ANDROID_SDK_ROOT, then ANDROID_HOME."""
    return os.getenv("ANDROID_SDK_ROOT") or os.getenv("ANDROID_HOME")


def sdk_tool(name):
    """Find command-line tools in known SDK layouts before falling back to PATH."""
    root = android_sdk_root()
    candidates = []
    if root:
        exe = f"{name}.bat" if platform.system() == "Windows" else name
        candidates += [
            Path(root) / "cmdline-tools" / "latest" / "bin" / exe,
            Path(root) / "cmdline-tools" / "bin" / exe,
            Path(root) / "tools" / "bin" / exe,
        ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return which(name)


def emulator_path():
    """Find the SDK's platform-specific emulator executable or its PATH alternative."""
    root = android_sdk_root()
    exe = "emulator.exe" if platform.system() == "Windows" else "emulator"
    if root and (Path(root) / "emulator" / exe).exists():
        return str(Path(root) / "emulator" / exe)
    return which("emulator")


def adb_path():
    """Find SDK platform-tools ADB or PATH; market helpers do not yet share this lookup."""
    root = android_sdk_root()
    exe = "adb.exe" if platform.system() == "Windows" else "adb"
    if root and (Path(root) / "platform-tools" / exe).exists():
        return str(Path(root) / "platform-tools" / exe)
    return which("adb")


def _adb_serials(adb):
    """List authorized ADB targets to avoid emulator serial collisions."""
    lines = _run([adb, "devices"], check=False).splitlines()
    return {
        line.split()[0]
        for line in lines
        if "\tdevice" in line and len(line.split()) >= 2
    }


def choose_emulator_port(adb=None, start=5554, stop=5680):
    """Choose a currently unused even console port and its deterministic emulator serial.
    
    The socket check is not a reservation; the single-run lock does not cover
    other programs that could claim the port before emulator startup."""
    used_serials = _adb_serials(adb) if adb else set()
    for port in range(start, stop + 1, 2):
        if f"emulator-{port}" in used_serials:
            continue
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.1)
        try:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                continue
        finally:
            sock.close()
        return port
    raise RuntimeError(f"No free Android emulator port found between {start} and {stop}.")


def _delete_avd(avdmanager, avd):
    """Request deletion of the named virtual device; failure is ignored by the baseline."""
    _run([avdmanager, "delete", "avd", "--name", avd], check=False)


def _create_avd(avdmanager, image, avd, device):
    """Create/replace a named AVD with the requested SDK image and device profile."""
    try:
        p = subprocess.run(
            [
                avdmanager, "create", "avd", "--force", "--name", avd,
                "--package", image, "--device", device,
            ],
            input="no\n", text=True, capture_output=True, timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("AVD creation timed out after 120 seconds") from exc
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout or "AVD creation failed").strip())


def prepare_android(
    api,
    avd,
    image_tag="google_apis",
    abi="x86_64",
    device="pixel",
    recreate=True,
    boot_timeout_seconds=240,
    log_root=None,
):
    """Install the requested image, launch an isolated emulator, and verify actual API level.
    
    The returned handle owns its process, ADB path, serial, port, and log. Data is
    wiped and animations disabled on this virtual target; errors attempt cleanup."""
    sdkmanager = sdk_tool("sdkmanager")
    avdmanager = sdk_tool("avdmanager")
    emulator = emulator_path()
    adb = adb_path()
    missing = [
        name
        for name, value in [
            ("sdkmanager", sdkmanager),
            ("avdmanager", avdmanager),
            ("emulator", emulator),
            ("adb", adb),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError("Missing Android tools: " + ", ".join(missing))

    image = f"system-images;android-{api};{image_tag};{abi}"
    _run([sdkmanager, "platform-tools", "emulator", image], check=True, timeout=900)

    if recreate:
        _delete_avd(avdmanager, avd)
        _create_avd(avdmanager, image, avd, device)
    else:
        existing = _run([emulator, "-list-avds"], check=False).splitlines()
        if avd not in existing:
            _create_avd(avdmanager, image, avd, device)

    port = choose_emulator_port(adb)
    serial = f"emulator-{port}"
    log_dir = private_dir(log_root or (Path.cwd() / "runs" / "emulator-logs"))
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", avd)
    log = log_dir / f"{safe_name}-{uuid.uuid4().hex[:8]}.emulator.log"
    log_handle = log.open("w", encoding="utf-8")
    private_file(log)
    proc = subprocess.Popen(
        [
            emulator,
            "-avd",
            avd,
            "-port",
            str(port),
            "-no-window",
            "-no-audio",
            "-no-boot-anim",
            "-no-snapshot",
            "-wipe-data",
        ],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    log_handle.close()

    info = {
        "udid": serial,
        "port": port,
        "process": proc,
        "log": str(log),
        "adb": adb,
        "requestedApiLevel": str(api),
        "systemImage": image,
    }

    try:
        deadline = time.time() + int(boot_timeout_seconds)
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"Android emulator {avd} exited during startup. See {log}."
                )
            serials = _adb_serials(adb)
            if serial in serials:
                complete = _run(
                    [adb, "-s", serial, "shell", "getprop", "sys.boot_completed"],
                    check=False,
                ).strip()
                if complete == "1":
                    break
            time.sleep(2)
        else:
            raise RuntimeError(
                f"Android emulator {avd} ({serial}) did not boot within "
                f"{boot_timeout_seconds} seconds. See {log}."
            )

        actual_api = _run(
            [adb, "-s", serial, "shell", "getprop", "ro.build.version.sdk"],
            check=True,
        ).strip()
        if actual_api != str(api):
            raise RuntimeError(
                f"Android AVD runtime mismatch: requested API {api}, "
                f"but {serial} booted API {actual_api}."
            )

        for key in [
            "window_animation_scale",
            "transition_animation_scale",
            "animator_duration_scale",
        ]:
            _run(
                [adb, "-s", serial, "shell", "settings", "put", "global", key, "0"],
                check=False,
            )

        info["actualApiLevel"] = actual_api
        return info
    except Exception:
        stop_android(info)
        raise


def stop_android(info):
    """Kill the owned emulator by explicit serial, then wait/terminate/kill its process."""
    if not info:
        return
    try:
        _run([info["adb"], "-s", info["udid"], "emu", "kill"], check=False)
    except Exception:
        pass
    proc = info.get("process")
    if proc is not None:
        try:
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def ios_runtimes():
    """Return available Xcode simulator runtimes on macOS, or an empty list on other hosts."""
    if platform.system() != "Darwin":
        return []
    data = json.loads(_run(["xcrun", "simctl", "list", "runtimes", "-j"]))
    return [runtime for runtime in data["runtimes"] if runtime.get("isAvailable")]


def _matching_ios_runtime(runtime_version):
    """Select an exact version first, then an unambiguous runtime name match."""
    requested = str(runtime_version)
    runtimes = ios_runtimes()
    exact = [r for r in runtimes if str(r.get("version")) == requested]
    if exact:
        return exact[0]
    named = [r for r in runtimes if requested in r.get("name", "")]
    if len(named) == 1:
        return named[0]
    if len(named) > 1:
        raise RuntimeError(
            f"iOS runtime value {requested!r} is ambiguous. Use an exact version."
        )
    raise RuntimeError(f"iOS Simulator runtime {requested} is not installed.")


def prepare_ios(runtime_version, device_type, sim_name, recreate=True):
    """Create/reuse and boot a named simulator, verifying its requested runtime identifier.
    
    Matching/mismatched named simulators can be deleted. These operations must not
    be used as physical iPhone or market-installed app reset mechanisms."""
    if platform.system() != "Darwin":
        raise RuntimeError("iOS Simulator testing requires macOS with Xcode.")

    runtime = _matching_ios_runtime(runtime_version)
    dtypes = json.loads(_run(["xcrun", "simctl", "list", "devicetypes", "-j"]))[
        "devicetypes"
    ]
    dtype = next((d for d in dtypes if d["name"] == device_type), None)
    if not dtype:
        raise RuntimeError(f"Simulator device type {device_type!r} is not installed.")

    devices = json.loads(_run(["xcrun", "simctl", "list", "devices", "-j"]))[
        "devices"
    ]
    matching = []
    mismatched = []
    for runtime_id, group in devices.items():
        for device in group:
            if device.get("name") != sim_name or not device.get("isAvailable", False):
                continue
            if runtime_id == runtime["identifier"]:
                matching.append(device)
            else:
                mismatched.append(device)

    if recreate:
        for device in matching + mismatched:
            _run(["xcrun", "simctl", "shutdown", device["udid"]], check=False)
            _run(["xcrun", "simctl", "delete", device["udid"]], check=False)
        matching = []
    else:
        # Remove same-name simulators tied to the wrong runtime so they can never be reused.
        for device in mismatched:
            _run(["xcrun", "simctl", "shutdown", device["udid"]], check=False)
            _run(["xcrun", "simctl", "delete", device["udid"]], check=False)

    if matching:
        udid = matching[0]["udid"]
    else:
        udid = _run(
            [
                "xcrun",
                "simctl",
                "create",
                sim_name,
                dtype["identifier"],
                runtime["identifier"],
            ]
        )

    _run(["xcrun", "simctl", "boot", udid], check=False)
    _run(["xcrun", "simctl", "bootstatus", udid, "-b"], timeout=300)

    # Verify the created/reused simulator still belongs to the requested runtime.
    current = json.loads(_run(["xcrun", "simctl", "list", "devices", "-j"]))[
        "devices"
    ]
    valid = any(
        runtime_id == runtime["identifier"]
        and any(device.get("udid") == udid for device in group)
        for runtime_id, group in current.items()
    )
    if not valid:
        raise RuntimeError(
            f"iOS simulator runtime mismatch for {sim_name}: requested {runtime_version}."
        )

    return {
        "udid": udid,
        "runtimeVersion": str(runtime.get("version")),
        "runtimeIdentifier": runtime["identifier"],
    }


def stop_ios(info):
    """Attempt to shut down only the returned simulator UDID; shutdown errors are ignored."""
    if not info:
        return
    try:
        _run(["xcrun", "simctl", "shutdown", info["udid"]], check=False)
    except Exception:
        pass
