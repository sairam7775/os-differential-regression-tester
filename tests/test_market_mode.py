"""Synthetic provenance and market-runtime checks, not device validation.

The iOS metadata test supplies a partial Appium mock and currently depends on
runner/options being importable through other test setup. Run this module alone
as well as in discovery when stabilizing the mocks; see tests/README.md.
"""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from osdiff.market import validate_market_pair, market_runtime, _normalize_ios_apps, _extract_android_version


def device(role="baseline", **overrides):
    """Build synthetic market facts with role-specific IDs/OS versions; no device is contacted."""
    base = {
        "platform": "android",
        "physicalDevice": True,
        "deviceId": "OLD123" if role == "baseline" else "NEW456",
        "manufacturer": "Google",
        "model": "Pixel 9",
        "deviceName": "tokay",
        "osVersion": "15" if role == "baseline" else "16",
        "apiLevel": "35" if role == "baseline" else "36",
        "appId": "com.example.market",
        "appVersion": "8.4.2",
        "appBuild": "84201",
        "appActivity": ".MainActivity",
        "marketOriginVerified": True,
        "toolInstalledApp": False,
    }
    base.update(overrides)
    return base


class MarketModeTests(unittest.TestCase):
    def test_valid_pair_requires_same_market_build_and_different_os(self):
        result = validate_market_pair(device("baseline"), device("candidate"))
        self.assertTrue(result["valid"])
        self.assertTrue(result["sameAppVersionAndBuild"])

    def test_version_mismatch_invalid(self):
        result = validate_market_pair(
            device("baseline"), device("candidate", appVersion="8.4.3")
        )
        self.assertFalse(result["valid"])
        self.assertIn("app_version_mismatch", result["errors"])

    def test_build_mismatch_invalid(self):
        result = validate_market_pair(
            device("baseline"), device("candidate", appBuild="84202")
        )
        self.assertFalse(result["valid"])
        self.assertIn("app_build_mismatch", result["errors"])

    def test_unverified_market_origin_invalid(self):
        result = validate_market_pair(
            device("baseline"), device("candidate", marketOriginVerified=False)
        )
        self.assertFalse(result["valid"])
        self.assertIn("candidate_market_origin_not_verified", result["errors"])

    def test_same_os_invalid(self):
        result = validate_market_pair(
            device("baseline"), device("candidate", osVersion="15", apiLevel="35")
        )
        self.assertFalse(result["valid"])
        self.assertIn("os_identity_must_differ", result["errors"])

    def test_hardware_mismatch_warning_or_error(self):
        b = device("baseline")
        c = device("candidate", model="Pixel 10")
        relaxed = validate_market_pair(b, c, require_same_model=False)
        self.assertTrue(relaxed["valid"])
        self.assertTrue(relaxed["warnings"])
        strict = validate_market_pair(b, c, require_same_model=True)
        self.assertFalse(strict["valid"])
        self.assertIn("hardware_model_mismatch", strict["errors"])

    def test_same_marketing_version_but_different_patch_build_is_valid(self):
        b = device("baseline", osVersion="15", apiLevel="35", securityPatch="2026-09-01", buildFingerprint="build-a")
        c = device("candidate", osVersion="15", apiLevel="35", securityPatch="2026-10-01", buildFingerprint="build-b")
        result = validate_market_pair(b, c)
        self.assertTrue(result["valid"])

    def test_missing_version_build_never_reports_same_app(self):
        result = validate_market_pair(
            device("baseline", appVersion=None, appBuild=None),
            device("candidate", appVersion=None, appBuild=None),
        )
        self.assertFalse(result["sameAppVersionAndBuild"])

    def test_strict_model_matching_fails_when_model_unverified(self):
        result = validate_market_pair(
            device("baseline", model="iPhone", modelVerified=False),
            device("candidate", model="iPhone", modelVerified=False),
            require_same_model=True,
        )
        self.assertFalse(result["valid"])
        self.assertIn("hardware_model_unverified", result["errors"])

    def test_environment_mismatch_invalid_by_default(self):
        result = validate_market_pair(
            device("baseline", environment={"locale":"en-US"}),
            device("candidate", environment={"locale":"ja-JP"}),
        )
        self.assertFalse(result["valid"])
        self.assertIn("environment_mismatch:locale", result["errors"])

    def test_market_runtime_never_supplies_app_binary(self):
        runtime = market_runtime(device("baseline"), "android")
        self.assertTrue(runtime["preinstalled"])
        self.assertTrue(runtime["noReset"])
        self.assertIsNone(runtime["appPath"])
        self.assertEqual(runtime["appPackage"], "com.example.market")

    def test_ios_list_apps_uses_return_attributes_contract(self):
        import osdiff.market as market_module

        calls = []
        class Driver:
            capabilities = {"platformVersion": "26.0", "deviceName": "iPhone"}
            def execute_script(self, name, args):
                calls.append((name, args))
                if name == "mobile: deviceInfo":
                    return {"productType": "iPhone17,3", "buildVersion": "23A1", "name": "Test iPhone"}
                if name == "mobile: listApps":
                    return {"com.example.market": {"CFBundleVersion": "10", "CFBundleShortVersionString": "1.0"}}
                return {}
            def get_window_size(self): return {"width": 390, "height": 844}
            def quit(self): pass

        with patch.object(market_module.platform, "system", return_value="Darwin"), \
             patch.object(market_module, "_physical_ios_device_ids", return_value={"UDID"}), \
             patch.object(market_module, "_new_probe_session", return_value=Driver()):
            result = market_module.probe_ios_market_device(
                "http://127.0.0.1:4723", "UDID", "com.example.market", True
            )
        list_call = next(args for name, args in calls if name == "mobile: listApps")
        self.assertIn("returnAttributes", list_call)
        self.assertNotIn("attributes", list_call)
        self.assertEqual(result["model"], "iPhone17,3")
        self.assertTrue(result["modelVerified"])

    def test_market_runtime_android_uses_clear_data_reset(self):
        runtime = market_runtime(device("baseline"), "android")
        self.assertEqual(runtime["resetStrategy"], "android_clear_data")

    def test_android_version_parsing(self):
        dump = "Package [com.example.market] versionCode=84201 targetSdk=36\nversionName=8.4.2"
        version, build = _extract_android_version(dump)
        self.assertEqual(version, "8.4.2")
        self.assertEqual(build, "84201")

    def test_ios_app_list_normalization(self):
        raw = {
            "com.example.market": {
                "CFBundleVersion": "10",
                "CFBundleShortVersionString": "1.0",
            }
        }
        apps = _normalize_ios_apps(raw)
        self.assertEqual(apps[0]["CFBundleIdentifier"], "com.example.market")


if __name__ == "__main__":
    unittest.main()
