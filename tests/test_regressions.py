"""Artifact comparison, HTML escaping, and scenario-ordering regressions.

Fixtures are temporary synthetic PNG/XML/JSON files. A runner import, including
one satisfied by another module's stubs, is not a real Appium integration check.
The optional runner test skips only when that import fails.
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

from osdiff.compare import compare_platform, hierarchy_ratio, write_report

try:
    from osdiff import runner
    APPIUM_CLIENT_AVAILABLE = True
except ModuleNotFoundError:
    runner = None
    APPIUM_CLIENT_AVAILABLE = False


class ComparatorRegressionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "pixelThreshold": 18,
            "visualBlurRadius": 0,
            "changedPixelRatioWarning": 0.01,
            "changedPixelRatioFailure": 0.05,
            "meanDifferenceWarning": 0.015,
            "durationRegressionFactor": 1.75,
            "minimumDurationRegressionSeconds": 1.0,
            "hierarchyChangeWarningRatio": 0.15,
            "hierarchyAttributes": ["class", "resource-id", "enabled"],
            "ignoreRegions": {"android": [], "ios": []},
        }

    def _write_summary(self, root, target, entries):
        path = root / "android" / target
        path.mkdir(parents=True, exist_ok=True)
        (path / "run-summary.json").write_text(json.dumps(entries), encoding="utf-8")

    def _checkpoint(self, root, target, scenario="flow", cp="home", color=(255, 255, 255)):
        folder = root / "android" / target / scenario / cp
        folder.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (100, 200), color).save(folder / "screen.png")
        (folder / "source.xml").write_text(
            '<hierarchy><node class="Button" resource-id="home" enabled="true"/></hierarchy>',
            encoding="utf-8",
        )
        state = {
            "assertions": [{"type": "element_present", "passed": True, "message": "ok"}],
            "recentActions": [{"type": "tap", "status": "passed", "durationSeconds": 0.2}],
        }
        (folder / "state.json").write_text(json.dumps(state), encoding="utf-8")

    def test_zero_checkpoints_is_invalid_not_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_summary(root, "baseline", [{"scenario": "flow", "status": "passed"}])
            self._write_summary(root, "candidate", [{"scenario": "flow", "status": "passed"}])
            results = compare_platform(root, "android", self.cfg, root / "report")
            summary = write_report(root / "report", results, "Test")
            self.assertGreater(summary["invalid"], 0)
            self.assertTrue(any("no_checkpoints_captured" in r["reasons"] for r in results))

    def test_baseline_failure_marks_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_summary(root, "baseline", [{"scenario": "flow", "status": "failed", "error": "login broken"}])
            self._write_summary(root, "candidate", [{"scenario": "flow", "status": "passed"}])
            self._checkpoint(root, "baseline")
            self._checkpoint(root, "candidate")
            results = compare_platform(root, "android", self.cfg, root / "report")
            self.assertTrue(any(r.get("comparisonStatus") == "INVALID" for r in results))

    def test_candidate_failure_after_checkpoint_is_critical(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_summary(root, "baseline", [{"scenario": "flow", "status": "passed"}])
            self._write_summary(root, "candidate", [{"scenario": "flow", "status": "failed", "error": "logout tap failed"}])
            self._checkpoint(root, "baseline")
            self._checkpoint(root, "candidate")
            results = compare_platform(root, "android", self.cfg, root / "report")
            execution = [r for r in results if "candidate_execution_failed" in r.get("reasons", [])]
            self.assertEqual(len(execution), 1)
            self.assertEqual(execution[0]["riskScore"], 98)
            summary = write_report(root / "report", results, "Test")
            self.assertEqual(summary["invalid"], 0)
            self.assertGreater(summary["highRisk"], 0)

    def test_duplicate_hierarchy_nodes_are_not_lost(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / "a.xml"
            b = root / "b.xml"
            a.write_text('<hierarchy><node class="Button" resource-id="x"/><node class="Button" resource-id="x"/></hierarchy>')
            b.write_text('<hierarchy><node class="Button" resource-id="x"/></hierarchy>')
            self.assertGreater(hierarchy_ratio(a, b, self.cfg), 0.0)

    def test_report_html_escapes_dynamic_values(self):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td)
            results = [{
                "platform": "android",
                "scenario": "<script>alert(1)</script>",
                "checkpoint": "home",
                "comparisonStatus": "PASS",
                "riskScore": 0,
                "severity": "Low",
                "reasons": [],
                "behaviorRegressions": [],
                "hierarchyChangeRatio": 0.0,
                "visual": {},
                "missingBaseline": False,
                "missingCandidate": False,
            }]
            write_report(report, results, "<b>unsafe</b>")
            text = (report / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", text)
            self.assertIn("&lt;script&gt;", text)
            self.assertNotIn("<b>unsafe</b> —", text)


@unittest.skipUnless(APPIUM_CLIENT_AVAILABLE, "Appium Python client not installed; run setup-local first")
class RunnerOrderingTests(unittest.TestCase):
    def test_checkpoint_assertions_run_before_capture(self):
        events = []

        class FakeDriver:
            page_source = "<hierarchy/>"
            def save_screenshot(self, path):
                events.append("screenshot")
                Image.new("RGB", (10, 10), "white").save(path)
            def get_window_size(self):
                return {"width": 10, "height": 10}

        def fake_assertion(driver, platform, assertion):
            events.append("assertion")
            return {"type": "element_present", "passed": True, "message": "ok"}

        with tempfile.TemporaryDirectory() as td, patch.object(runner, "_assertion", side_effect=fake_assertion):
            step = {"type": "checkpoint", "id": "home", "assertions": [{"type": "element_present"}], "settleSeconds": 0}
            runner._checkpoint(FakeDriver(), "android", "flow", step, [], Path(td), 0)
            self.assertEqual(events[:2], ["assertion", "screenshot"])


class PathResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("osdiff_cli", ROOT / "osdiff.py")
        cls.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cli)

    def test_tool_root_is_script_directory(self):
        self.assertEqual(self.cli.TOOL_ROOT, ROOT)

    def test_relative_paths_resolve_from_config_directory(self):
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / "config"
            config_dir.mkdir()
            cfg = {"_configDir": str(config_dir)}
            resolved = self.cli.resolve_path(cfg, "../apps/app.apk")
            self.assertEqual(Path(resolved), (Path(td) / "apps" / "app.apk").resolve())


if __name__ == "__main__":
    unittest.main()
