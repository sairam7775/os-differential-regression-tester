"""Synthetic regression cases for Claude/Codex review findings; no devices or SDK stubs."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from osdiff import crawler, fsutil, market, runner


def cli_module():
    spec = importlib.util.spec_from_file_location("review_cli", ROOT / "osdiff.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def android(body):
    return f'<hierarchy>{body}</hierarchy>'


def button(label, rid="shared", enabled="true", child=""):
    return f'<node class="android.widget.Button" resource-id="{rid}" text="{label}" enabled="{enabled}" clickable="true" bounds="[0,0][20,20]">{child}</node>'


class Element:
    def __init__(self, node):
        self.node = node
        self.clicked = 0
        self.typed = []
    def get_attribute(self, name):
        name = {"resourceId":"resource-id", "className":"class", "contentDescription":"content-desc"}.get(name, name)
        return self.node.attrib.get(name)
    def find_elements(self, *args):
        return [Element(child) for child in self.node.iter() if child is not self.node]
    def clear(self):
        self.typed.clear()
    def send_keys(self, value):
        self.typed.append(value)
    def click(self):
        self.clicked += 1


class Driver:
    current_package = "com.app"
    current_activity = ".Main"
    def __init__(self, source):
        self.page_source = source
        self.elements = [Element(n) for n in ET.fromstring(source).iter()]
        self.closed = False
    def find(self, locator):
        return [e for e in self.elements if crawler._locator_matches(e.node, locator)]
    def quit(self):
        self.closed = True


class SafeControlTests(unittest.TestCase):
    def test_nested_dangerous_android_rows_are_blocked(self):
        for text in ("Delete account", "Print label", "Pair printer", "Update firmware"):
            for child in (f'<node text="{text}"/>', f'<node><node text="{text}"/></node>'):
                with self.subTest(text=text, nested="<node><node" in child):
                    actions, blocked, _ = crawler.discover_actions(android(button("",child=child)), "android", {})
                    self.assertEqual(actions, [])
                    self.assertTrue(blocked)

    def test_ios_cell_child_caption_is_blocked(self):
        source = '<App><node type="XCUIElementTypeCell" x="0" y="0" width="20" height="20"><node type="XCUIElementTypeStaticText" label="Purchase now" x="0" y="0" width="10" height="10"/></node></App>'
        actions, blocked, _ = crawler.discover_actions(source, "ios", {})
        self.assertFalse(actions)
        self.assertTrue(blocked)

    def test_required_deny_forms_and_safe_labels(self):
        config = json.loads((ROOT/"config/local-config.json").read_text())["crawler"]
        for label in ("Unpair", "Pairing device", "Disconnect", "Connecting", "Connected devices", "Forget device", "Payment", "Purchases", "Checkout", "Reorder", "Clear storage", "Force stop", "Install", "Update now", "USB debugging", "Airplane mode", "Reprint"):
            with self.subTest(label=label):
                self.assertIsNotNone(crawler._danger_reason(label, config))
        for label in ("Continue", "Next", "Not now", "Settings", "Preview"):
            with self.subTest(label=label):
                self.assertIsNone(crawler._danger_reason(label, config))

    def test_config_cannot_remove_mandatory_protection(self):
        self.assertIsNotNone(crawler._danger_reason("Print", {"denyKeywords":[]}))

    def test_blocked_and_disabled_nodes_do_not_shift_live_ordinals(self):
        source = android(button("Print") + button("Hidden",enabled="false") + button("Settings"))
        action = crawler.discover_actions(source,"android",{})[0][0]
        self.assertEqual(action["ordinal"], 2)
        driver = Driver(source)
        with patch.object(crawler,"_find_elements",side_effect=lambda d,l:d.find(l)):
            crawler._tap(driver,"android",action,{})
        self.assertEqual([e.clicked for e in driver.elements], [0,0,0,1])

    def test_fallback_locator_has_its_own_occurrence(self):
        source = android(button("A") + button("Settings"))
        actions = crawler.discover_actions(source,"android",{})[0]
        action = next(a for a in actions if a["label"] == "Settings")
        self.assertEqual(action["locators"][0]["ordinal"],1)
        self.assertEqual(action["locators"][1]["ordinal"],0)
        driver=Driver(source)
        with patch.object(crawler,"_find_elements",side_effect=lambda d,l:[] if l["strategy"]=="id" else d.find(l)):
            crawler._tap(driver,"android",action,{})
        self.assertEqual(driver.elements[-1].clicked,1)

    def test_changed_live_control_is_not_clicked(self):
        source=android(button("Settings"))
        action=crawler.discover_actions(source,"android",{})[0][0]
        driver=Driver(android(button("Print")))
        with self.assertRaises(RuntimeError):
            crawler._tap(driver,"android",action,{})
        self.assertEqual(driver.elements[-1].clicked,0)

    def test_live_descendant_changed_after_source_capture_is_blocked(self):
        source=android(button("Settings"))
        action=crawler.discover_actions(source,"android",{})[0][0]
        driver=Driver(source)
        ET.SubElement(driver.elements[-1].node,"node",text="Delete account")
        with patch.object(crawler,"_find_elements",side_effect=lambda d,l:d.find(l)):
            with self.assertRaises(RuntimeError):
                crawler._tap(driver,"android",action,{})
        self.assertEqual(driver.elements[-1].clicked,0)

    def test_legacy_unverified_action_has_no_coordinate_fallback(self):
        with self.assertRaises(RuntimeError):
            crawler._tap(Driver(android(button("Settings"))),"android",{"kind":"tap","bounds":{"x":1,"y":1,"width":10,"height":10}}, {})


class ForegroundTests(unittest.TestCase):
    def test_settings_and_installer_are_rejected_even_if_configured(self):
        driver=Driver(android(button("Settings")))
        for package in ("com.android.settings","com.android.packageinstaller","com.other"):
            with self.subTest(package=package):
                driver.current_package=package
                with self.assertRaises(RuntimeError):
                    crawler._assert_allowed_foreground(driver,"android",{"appPackage":"com.app"},{"allowedSystemPackages":{"android":[package]}},after_activation=True)

    def test_recognized_permission_dialog_can_queue_only_permission_buttons(self):
        source=android(button("Allow",rid="com.android.permissioncontroller:id/permission_allow_button")+button("Help",rid="other"))
        driver=Driver(source)
        driver.current_package="com.android.permissioncontroller"
        context=crawler._assert_allowed_foreground(driver,"android",{"appPackage":"com.app"},{})
        actions, _, _=crawler.discover_actions(source,"android",{},context=context)
        self.assertEqual([a["label"] for a in actions],["Allow"])

    def test_unrecognized_permission_surface_is_rejected(self):
        driver=Driver(android(button("Settings")))
        driver.current_package="com.android.permissioncontroller"
        with self.assertRaises(RuntimeError):
            crawler._assert_allowed_foreground(driver,"android",{"appPackage":"com.app"},{})

    def test_external_navigation_produces_partial_without_queuing_system_paths(self):
        driver=Driver(android(button("Settings")))
        driver.current_package="com.android.settings"
        with tempfile.TemporaryDirectory() as td, patch.object(crawler,"_new_driver",return_value=driver), patch.object(crawler,"_prepare_path",return_value=True):
            graph=crawler.crawl_baseline("url",{"udid":"synthetic","appPackage":"com.app"},"android",Path(td),{"settleSeconds":0})
        self.assertEqual(graph["coverageStatus"],"PARTIAL")
        self.assertFalse(graph["edges"])
        self.assertFalse(graph["screens"])


class InputAndPrivacyTests(unittest.TestCase):
    def test_unrelated_labels_never_receive_password(self):
        cfg=json.loads((ROOT/"config/local-config.json").read_text())["crawler"]
        for label in ("Search shopping","Shipping address","shipping_address","Spinner","Typing indicator","PIN"):
            source=android(f'<node class="android.widget.EditText" resource-id="field" text="{label}" password="false"/>')
            driver=Driver(source)
            with self.subTest(label=label), patch.dict(os.environ,{"TEST_USER_PASSWORD":"synthetic-secret"}), patch.object(crawler,"_find_elements",side_effect=lambda d,l:d.find(l)):
                filled,blocked=crawler.fill_known_inputs(driver,"android",source,cfg)
                self.assertFalse(filled)
                self.assertTrue(blocked)
                self.assertFalse(driver.elements[-1].typed)

    def test_verified_secure_pin_field_receives_secret(self):
        cfg=json.loads((ROOT/"config/local-config.json").read_text())["crawler"]
        source=android('<node class="android.widget.EditText" resource-id="field" text="PIN" password="true"/>')
        driver=Driver(source)
        with patch.dict(os.environ,{"TEST_USER_PASSWORD":"synthetic-secret"}), patch.object(crawler,"_find_elements",side_effect=lambda d,l:d.find(l)):
            filled,blocked=crawler.fill_known_inputs(driver,"android",source,cfg)
        self.assertTrue(filled)
        self.assertFalse(blocked)
        self.assertEqual(driver.elements[-1].typed,["synthetic-secret"])

    def test_secret_rule_on_plain_field_is_blocked_even_with_old_unbounded_pattern(self):
        source=android('<node class="android.widget.EditText" text="Shipping" password="false"/>')
        filled,blocked=crawler.fill_known_inputs(Driver(source),"android",source,{"autoInputRules":[{"pattern":"pin","value":"synthetic","secret":True}]})
        self.assertFalse(filled)
        self.assertEqual(blocked[0]["reason"],"secret_requires_secure_field")

    def test_xml_redaction_preserves_parseability_and_handles_encoded_secrets(self):
        source='<hierarchy><node text="a&amp;b&quot;c">a&amp;b"c</node></hierarchy>'
        value=fsutil.redact_xml(source,['a&b"c'])
        root=ET.fromstring(value)
        self.assertEqual(root[0].attrib["text"],"[REDACTED]")
        self.assertEqual(root[0].text,"[REDACTED]")

    def test_nested_metadata_redacts_credentials_and_device_ids(self):
        values=["synthetic-secret","synthetic-serial"]
        data={"trace":[{"error":"synthetic-secret at synthetic-serial"}],"assertion":"synthetic-secret"}
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"evidence.json"
            fsutil.write_json(path,data,sensitive_values=values)
            text=path.read_text()
            self.assertNotIn("synthetic-secret",text)
            self.assertNotIn("synthetic-serial",text)
            self.assertIsInstance(json.loads(text)["trace"],list)

    def test_malformed_xml_is_not_repaired_into_valid_evidence(self):
        result=fsutil.redact_xml('<broken text="synthetic-secret"',["synthetic-secret"])
        self.assertNotIn("synthetic-secret",result)
        with self.assertRaises(ET.ParseError): ET.fromstring(result)


class OsIdentityTests(unittest.TestCase):
    def pair(self):
        b={"deviceId":"A","physicalDevice":True,"platform":"android","appId":"com.app","appVersion":"1","appBuild":"10","manufacturer":"Google","model":"Pixel 6","marketOriginVerified":True,"osVersion":"14","apiLevel":"34","securityPatch":"2026-09-01","buildFingerprint":"google/oriole/oriole:14/UP1A/123:user/release-keys"}
        c=dict(b,deviceId="B",model="Pixel 7",buildFingerprint="google/panther/panther:14/UP1A/123:user/release-keys")
        return b,c
    def test_hardware_only_fingerprint_difference_is_invalid(self):
        result=market.validate_market_pair(*self.pair())
        self.assertFalse(result["valid"])
        self.assertIn("os_identity_must_differ",result["errors"])
    def test_patch_difference_is_positive_os_evidence(self):
        b,c=self.pair(); c["securityPatch"]="2026-10-01"
        self.assertTrue(market.validate_market_pair(b,c)["valid"])
    def test_build_id_difference_is_positive_os_evidence(self):
        b,c=self.pair(); c["buildFingerprint"]="google/panther/panther:14/UP1B/124:user/release-keys"
        self.assertTrue(market.validate_market_pair(b,c)["valid"])
    def test_missing_os_components_do_not_create_a_difference(self):
        b,c=self.pair()
        for key in ("osVersion","apiLevel","securityPatch","buildFingerprint"): c[key]=None
        self.assertFalse(market.validate_market_pair(b,c)["valid"])
    def test_physical_identity_is_required(self):
        b,c=self.pair(); c.update(osVersion="15",physicalDevice=False)
        self.assertIn("physical_device_not_verified",market.validate_market_pair(b,c)["errors"])


class ResetAndLockTests(unittest.TestCase):
    def test_pid_is_not_used_for_state_identity(self):
        source=android('<node class="TextView" text="Home"/>')
        self.assertEqual(crawler.state_fingerprint(source,{}, {"bundleId":"com.app","pid":1}), crawler.state_fingerprint(source,{}, {"bundleId":"com.app","pid":2}))
    def test_failed_action_keeps_successful_reset_evidence(self):
        driver=Driver(android(button("Settings")))
        with patch.object(crawler,"_prepare_path",return_value=True), patch.object(crawler,"execute_action",side_effect=RuntimeError("synthetic failure")):
            used,trace,error,reset=crawler.replay_path("url",{"appPackage":"com.app"},"android",[{"kind":"tap"}],{},driver=driver)
        self.assertIsNone(used)
        self.assertTrue(error)
        self.assertTrue(reset)
        self.assertEqual(trace[0]["status"],"failed")
        self.assertFalse(driver.closed)
    def test_candidate_nondeterministic_reset_invalidates_branched_coverage(self):
        coverage=crawler.coverage_summary({"coverageStatus":"COMPLETE_WITHIN_POLICY","attemptedPaths":2,"deterministicReset":True},{"baselineScreens":2,"deterministicReset":False})
        self.assertEqual(coverage["coverageStatus"],"PARTIAL")
        self.assertEqual(coverage["resetIsolationStatus"],"NON_DETERMINISTIC")
    def test_candidate_blocked_inputs_invalidate_coverage(self):
        coverage=crawler.coverage_summary({"coverageStatus":"COMPLETE_WITHIN_POLICY","deterministicReset":True},{"deterministicReset":True,"blockedInputs":[{"reason":"missing_input"}]})
        self.assertEqual(coverage["coverageStatus"],"PARTIAL")
    def test_market_cannot_use_simulator_reinstall_even_with_binary(self):
        with self.assertRaises(RuntimeError), patch.object(crawler.subprocess,"run") as run:
            crawler._prepare_path(Driver(android(button("Settings"))),{"bundleId":"com.app","udid":"fake","preinstalled":True,"appPath":"fake.app","resetStrategy":"ios_simulator_reinstall"},"ios",{})
        run.assert_not_called()
    def test_empty_and_corrupt_kernel_lock_files_are_reusable(self):
        cli=cli_module()
        with tempfile.TemporaryDirectory() as td, patch.object(cli,"TOOL_ROOT",Path(td)):
            path=Path(td)/".osdiff-run.lock"
            for text in ("","bad metadata"):
                path.write_text(text)
                lock=cli._acquire_run_lock()
                with self.assertRaises(RuntimeError): cli._acquire_run_lock()
                cli._release_run_lock(lock)
                self.assertEqual(path.read_text(),"")
    def test_main_releases_lock_on_success_error_and_cancellation(self):
        cli=cli_module()
        for error, expected in ((None,0),(RuntimeError("synthetic"),1),(KeyboardInterrupt(),130)):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as td, patch.object(cli,"TOOL_ROOT",Path(td)), patch.object(sys,"argv",["osdiff","run","--platform","android"]), patch.object(cli,"run_cmd",return_value=0,side_effect=error):
                self.assertEqual(cli.main(),expected)
                lock=cli._acquire_run_lock(); cli._release_run_lock(lock)
    def test_second_process_cannot_acquire_held_kernel_lock(self):
        cli=cli_module()
        with tempfile.TemporaryDirectory() as td, patch.object(cli,"TOOL_ROOT",Path(td)):
            lock=cli._acquire_run_lock()
            code=f"import importlib.util; from pathlib import Path; s=importlib.util.spec_from_file_location('cli',{str(ROOT/'osdiff.py')!r}); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.TOOL_ROOT=Path({td!r}); m._acquire_run_lock()"
            try:
                result=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=15)
                self.assertNotEqual(result.returncode,0)
                self.assertIn("Another osdiff run",result.stderr)
            finally: cli._release_run_lock(lock)
    @unittest.skipUnless(os.name=="nt","Windows liveness API")
    def test_windows_liveness_never_calls_os_kill(self):
        cli=cli_module()
        with patch.object(cli.os,"kill",side_effect=AssertionError("os.kill must not run on Windows")):
            self.assertTrue(cli._pid_alive(os.getpid()))


if __name__ == "__main__":
    unittest.main()
