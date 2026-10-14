"""Synthetic crawler, report, and infrastructure regressions.

Pillow supplies image fixtures. Driver/process boundaries use scoped mocks;
installed Appium/Selenium modules are never replaced by global SDK stubs."""

import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Dependencies stay real; individual driver/process boundaries are mocked per test.
from osdiff import crawler
from osdiff.compare import compare_platform, write_report


class CrawlerHardeningTests(unittest.TestCase):
    def test_deny_keyword_wins_over_continue(self):
        cfg = {"denyKeywords": [r"\bpay\b", r"\bprint\b"], "allowKeywords": [r"\bcontinue\b"]}
        self.assertIsNotNone(crawler._danger_reason("Continue to Pay", cfg))
        self.assertIsNotNone(crawler._danger_reason("Continue to Print", cfg))

    def test_action_truncation_is_recorded(self):
        xml = '''<hierarchy>
          <node class="android.widget.Button" text="A" clickable="true" bounds="[0,0][10,10]"/>
          <node class="android.widget.Button" text="B" clickable="true" bounds="[10,0][20,10]"/>
        </hierarchy>'''
        actions, blocked, _ = crawler.discover_actions(xml, "android", {"maxActionsPerScreen": 1, "safeMode": True})
        self.assertEqual(len(actions), 1)
        self.assertTrue(any(x.get("reason") == "actions_truncated" for x in blocked))

    def test_android_fingerprint_distinguishes_text_only_pages(self):
        cfg = {"fingerprintAttributes": ["class", "resource-id", "text"]}
        a = '<hierarchy><node class="TextView" resource-id="title" text="Page one"/></hierarchy>'
        b = '<hierarchy><node class="TextView" resource-id="title" text="Page two"/></hierarchy>'
        self.assertNotEqual(crawler.state_fingerprint(a, cfg), crawler.state_fingerprint(b, cfg))

    def test_missing_ordinal_does_not_fall_back_to_first_element(self):
        with patch.object(crawler, "_find_elements", return_value=[object()]):
            action = {"ordinal": 1, "locators": [{"strategy": "id", "value": "same"}]}
            self.assertIsNone(crawler._find_for_action(object(), action))

    def test_replay_failure_forces_partial_coverage(self):
        fake_driver = object()
        with tempfile.TemporaryDirectory() as td, \
             patch.object(crawler, "_new_driver", return_value=fake_driver), \
             patch.object(crawler, "replay_path", return_value=(None, [], "boom", False)), \
             patch.object(crawler, "_close_driver"):
            graph = crawler.crawl_baseline(
                "http://127.0.0.1:4723",
                {"appPackage": "com.example", "udid": "X"},
                "android", Path(td), {"maxScreens": 5, "maxDepth": 2, "maxTotalPaths": 3},
            )
            self.assertEqual(graph["coverageStatus"], "PARTIAL")
            self.assertEqual(graph["baselineReplayFailures"], 1)

    def test_checkpoint_persists_action_trace(self):
        class Driver:
            page_source = '<hierarchy><node text="secret@example.com"/></hierarchy>'
            def save_screenshot(self, path): Image.new("RGB", (10, 10), "white").save(path)
            def get_window_size(self): return {"width": 10, "height": 10}
        trace = [{"status": "passed", "durationSeconds": 1.2, "action": {"kind": "tap"}}]
        with tempfile.TemporaryDirectory() as td:
            crawler._save_checkpoint(
                Driver(), "android", "cp", "abc", [], Path(td),
                {"sensitiveValues": ["secret@example.com"]}, recent_actions=trace,
            )
            state = json.loads((Path(td)/"auto_crawl"/"cp"/"state.json").read_text())
            source = (Path(td)/"auto_crawl"/"cp"/"source.xml").read_text()
            self.assertEqual(state["recentActions"], trace)
            self.assertNotIn("secret@example.com", source)

    def test_android_clear_data_reset_is_deterministic(self):
        class Driver:
            def terminate_app(self, app): return True
            def activate_app(self, app): return True
            @property
            def current_package(self): return "com.example"
            @property
            def current_activity(self): return ".MainActivity"
        completed = subprocess.CompletedProcess(["adb"], 0, stdout="Success\n", stderr="")
        runtime = {"appPackage":"com.example","udid":"SERIAL","resetStrategy":"android_clear_data","adbPath":"adb"}
        with patch.object(crawler.subprocess, "run", return_value=completed) as run:
            deterministic = crawler._prepare_path(Driver(), runtime, "android", {"settleSeconds":0, "resetTimeoutSeconds":5})
        self.assertTrue(deterministic)
        self.assertIn("pm", run.call_args.args[0])
        self.assertIn("clear", run.call_args.args[0])

    def test_unknown_ios_foreground_is_rejected(self):
        class Driver:
            def execute_script(self, name, args): return {"bundleId":"com.other.app"}
        with self.assertRaises(RuntimeError):
            crawler._assert_allowed_foreground(
                Driver(), "ios", {"bundleId":"com.example"}, {"allowedSystemPackages":{"ios":[]}}
            )

    def test_action_trace_drives_duration_regression(self):
        cfg = {
            "pixelThreshold":18, "visualBlurRadius":0, "changedPixelRatioWarning":0.01,
            "changedPixelRatioFailure":0.05, "meanDifferenceWarning":0.015,
            "durationRegressionFactor":1.75, "minimumDurationRegressionSeconds":1.0,
            "hierarchyChangeWarningRatio":0.15, "ignoreRegions":{"android":[]},
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for target, duration in (("baseline", 1.0), ("candidate", 3.0)):
                base = root/"android"/target
                cp = base/"auto_crawl"/"home"
                cp.mkdir(parents=True)
                (base/"run-summary.json").write_text(json.dumps([{"scenario":"auto_crawl","status":"passed"}]))
                Image.new("RGB", (10,10), "white").save(cp/"screen.png")
                (cp/"source.xml").write_text('<hierarchy><node class="Button" resource-id="x"/></hierarchy>')
                (cp/"state.json").write_text(json.dumps({
                    "recentActions":[{"status":"passed","durationSeconds":duration}], "assertions":[]
                }))
            results = compare_platform(root, "android", cfg, root/"report")
            cp = next(x for x in results if x["checkpoint"] == "home")
            self.assertIn("performance_regression", cp["reasons"])
            self.assertEqual(cp["comparisonStatus"], "REVIEW")


class ReportHardeningTests(unittest.TestCase):
    def test_partial_coverage_makes_report_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            summary = write_report(
                Path(td), [], "Test",
                coverage={"android": {"coverageStatus": "PARTIAL", "coverageNote": "blocked"}},
            )
            self.assertEqual(summary["overallStatus"], "INVALID")
            self.assertTrue(summary["coverageInvalid"])
            html = (Path(td)/"index.html").read_text(encoding="utf-8")
            self.assertIn("INVALID comparison", html)

    def test_malformed_hierarchy_is_invalid_not_identical(self):
        cfg = {
            "pixelThreshold": 18, "visualBlurRadius": 0,
            "changedPixelRatioWarning": 0.01, "changedPixelRatioFailure": 0.05,
            "meanDifferenceWarning": 0.015, "durationRegressionFactor": 1.75,
            "minimumDurationRegressionSeconds": 1.0, "hierarchyChangeWarningRatio": 0.15,
            "ignoreRegions": {"android": []},
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for target in ("baseline", "candidate"):
                base = root/"android"/target
                (base/"auto_crawl"/"home").mkdir(parents=True)
                (base/"run-summary.json").write_text(json.dumps([{"scenario":"auto_crawl","status":"passed"}]))
                Image.new("RGB", (10,10), "white").save(base/"auto_crawl"/"home"/"screen.png")
                (base/"auto_crawl"/"home"/"state.json").write_text(json.dumps({"recentActions":[],"assertions":[]}))
            (root/"android"/"baseline"/"auto_crawl"/"home"/"source.xml").write_text("<broken")
            (root/"android"/"candidate"/"auto_crawl"/"home"/"source.xml").write_text("<also-broken")
            results = compare_platform(root, "android", cfg, root/"report")
            cp = next(x for x in results if x["checkpoint"] == "home")
            self.assertEqual(cp["comparisonStatus"], "INVALID")
            self.assertIn("hierarchy_capture_invalid", cp["reasons"])


class InfrastructureHardeningTests(unittest.TestCase):
    def test_device_command_timeout_becomes_runtime_error(self):
        from osdiff import devices
        with patch.object(devices.subprocess, "run", side_effect=subprocess.TimeoutExpired(["adb"], 1)):
            with self.assertRaises(RuntimeError):
                devices._run(["adb"], timeout=1)

    def test_run_lock_blocks_second_writer(self):
        spec = importlib.util.spec_from_file_location("osdiff_cli_hardened", ROOT/"osdiff.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as td, patch.object(cli, "TOOL_ROOT", Path(td)):
            lock = cli._acquire_run_lock()
            try:
                with self.assertRaises(RuntimeError):
                    cli._acquire_run_lock()
            finally:
                cli._release_run_lock(lock)

    @unittest.skipIf(os.name == "nt", "POSIX permission assertion")
    def test_checkpoint_artifacts_are_owner_only(self):
        class Driver:
            page_source = '<hierarchy/>'
            def save_screenshot(self, path): Image.new("RGB", (10,10), "white").save(path)
            def get_window_size(self): return {"width":10,"height":10}
        with tempfile.TemporaryDirectory() as td:
            crawler._save_checkpoint(Driver(), "android", "cp", "id", [], Path(td), {}, recent_actions=[])
            folder = Path(td)/"auto_crawl"/"cp"
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
            self.assertEqual((folder/"source.xml").stat().st_mode & 0o777, 0o600)
            self.assertEqual((folder/"screen.png").stat().st_mode & 0o777, 0o600)

    def test_hardware_connect_keywords_are_blocked(self):
        cfg = {
            "safeMode": True,
            "denyKeywords": [r"\bpair\b", r"\bconnect(?:ion)?\b", r"\bbluetooth\b"],
            "allowKeywords": [r"\bcontinue\b"],
        }
        self.assertIsNotNone(crawler._danger_reason("Connect Bluetooth printer", cfg))
        self.assertIsNotNone(crawler._danger_reason("Continue to Pair", cfg))



if __name__ == "__main__":
    unittest.main()
