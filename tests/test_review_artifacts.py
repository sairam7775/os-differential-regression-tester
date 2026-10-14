"""Real Pillow artifacts exercise fail-closed comparison and capture privacy; no devices."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from PIL import Image
from osdiff import crawler, devices, runner
from osdiff.compare import compare_platform, write_report

ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'config/local-config.json').read_text())["comparison"]


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.folders={}
        for role in ("baseline","candidate"):
            base=self.root/'android'/role
            folder=base/'flow'/'home'
            folder.mkdir(parents=True)
            self.folders[role]=folder
            (base/'run-summary.json').write_text(json.dumps([{"scenario":"flow","status":"passed"}]))
            Image.new('RGB',(20,20),'white').save(folder/'screen.png')
            (folder/'source.xml').write_text('<hierarchy><node class="Button" resource-id="home" text="Home"/></hierarchy>')
            self.state(role,{"assertions":[{"type":"element_present","passed":True}],"recentActions":[{"type":"tap","status":"passed","durationSeconds":1}]})
    def state(self,role,value):
        (self.folders[role]/'state.json').write_text(json.dumps(value))
    def results(self):
        return compare_platform(self.root,'android',CONFIG,self.root/'report')
    def summary(self):
        return write_report(self.root/'report',self.results())
    def test_valid_artifacts_still_pass(self):
        self.assertEqual(self.summary()['overallStatus'],'PASS')
    def test_malformed_summary_is_invalid_despite_valid_checkpoints(self):
        for role in ("baseline","candidate"):
            (self.root/'android'/role/'run-summary.json').write_text('{bad')
        self.assertEqual(self.summary()['overallStatus'],'INVALID')
    def test_empty_and_duplicate_summaries_are_invalid(self):
        for value in ([],[{"scenario":"flow","status":"passed"}]*2):
            with self.subTest(value=value):
                (self.root/'android'/'baseline'/'run-summary.json').write_text(json.dumps(value))
                self.assertEqual(self.summary()['overallStatus'],'INVALID')
    def test_malformed_and_wrong_type_checkpoint_json_is_invalid(self):
        for value in ('{bad','[]','{}','{"assertions":null,"recentActions":[]}'):
            with self.subTest(value=value):
                (self.folders['baseline']/'state.json').write_text(value)
                self.assertEqual(self.summary()['overallStatus'],'INVALID')
    def test_failed_baseline_assertion_is_invalid(self):
        self.state('baseline',{"assertions":[{"passed":False}],"recentActions":[]})
        self.assertEqual(self.summary()['overallStatus'],'INVALID')
    def test_failed_baseline_action_is_invalid(self):
        self.state('baseline',{"assertions":[],"recentActions":[{"status":"failed","durationSeconds":1}]})
        self.assertEqual(self.summary()['overallStatus'],'INVALID')
    def test_nonboolean_assertion_is_invalid(self):
        self.state('baseline', {"assertions":[{"passed":1}], "recentActions":[]})
        self.assertEqual(self.summary()['overallStatus'],'INVALID')
    def test_missing_nonfinite_and_negative_timings_are_invalid(self):
        for duration in (None, "bad", True, float('nan'), float('inf'), -1):
            with self.subTest(duration=duration):
                self.state('candidate', {"assertions":[], "recentActions":[{"status":"passed", "durationSeconds":duration}]})
                self.assertEqual(self.summary()['overallStatus'],'INVALID')
    def test_missing_candidate_action_is_a_critical_regression(self):
        self.state('candidate',{"assertions":[{"passed":True}],"recentActions":[]})
        result=next(r for r in self.results() if r['checkpoint']=='home')
        self.assertEqual(result['comparisonStatus'],'FAIL')
        self.assertEqual(result['severity'],'Critical')
    def test_summary_failed_action_cannot_be_hidden_by_passed_status(self):
        path=self.root/'android'/'baseline'/'run-summary.json'
        path.write_text(json.dumps([{"scenario":"flow","status":"passed","actions":[{"status":"failed"}]}]))
        self.assertEqual(self.summary()['overallStatus'],'INVALID')
    def test_corrupt_image_produces_invalid_report(self):
        (self.folders['candidate']/'screen.png').write_text('not an image')
        self.assertEqual(self.summary()['overallStatus'],'INVALID')
    def test_empty_hierarchy_is_not_valid_comparison_evidence(self):
        (self.folders['candidate']/'source.xml').write_text('<hierarchy/>')
        self.assertEqual(self.summary()['overallStatus'],'INVALID')
    def test_text_change_is_part_of_default_hierarchy_comparison(self):
        (self.folders['candidate']/'source.xml').write_text('<hierarchy><node class="Button" resource-id="home" text="Wrong"/></hierarchy>')
        result=next(r for r in self.results() if r['checkpoint']=='home')
        self.assertGreater(result['hierarchyChangeRatio'],0)
    def test_empty_report_is_invalid(self):
        self.assertEqual(write_report(self.root/'empty',[])['overallStatus'],'INVALID')


class CaptureTests(unittest.TestCase):
    def test_secret_xml_capture_remains_valid_and_metadata_is_sanitized(self):
        class Driver:
            page_source='<hierarchy><node class="Text" text="synthetic-secret"/></hierarchy>'
            def save_screenshot(self,path): Image.new('RGB',(10,10),'white').save(path)
            def get_window_size(self): return {'width':10,'height':10}
        with tempfile.TemporaryDirectory() as td:
            crawler._save_checkpoint(Driver(),'android','cp','state',[],Path(td),{'sensitiveValues':['synthetic-secret'],'sensitiveDeviceIds':['synthetic-serial']},metadata={'error':'synthetic-secret at synthetic-serial'})
            folder=Path(td)/'auto_crawl'/'cp'
            source=(folder/'source.xml').read_text()
            ET.fromstring(source)
            self.assertNotIn('synthetic-secret',source)
            self.assertNotIn('synthetic-serial',(folder/'state.json').read_text())
    def test_failed_screenshot_does_not_write_successful_state(self):
        class Driver:
            def save_screenshot(self,path): return False
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError):
                crawler._save_checkpoint(Driver(),'android','cp','state',[],Path(td),{})
            self.assertFalse((Path(td)/'auto_crawl'/'cp'/'state.json').exists())
    def test_continued_action_failure_keeps_scenario_failed_and_quits(self):
        class Driver:
            closed=False
            def quit(self): self.closed=True
        driver=Driver()
        with tempfile.TemporaryDirectory() as td,patch.object(runner,'_new_session',return_value=driver),patch.object(runner,'_execute',side_effect=RuntimeError('synthetic failure')):
            result=runner.run_scenario('url',{'udid':'synthetic-serial'},'android',{'name':'flow','steps':[{'type':'tap','continueOnFailure':True}]},Path(td))
        self.assertEqual(result['status'],'failed')
        self.assertTrue(driver.closed)
    def test_inline_scenario_secret_is_redacted_from_failure(self):
        class Driver:
            def quit(self): pass
        with tempfile.TemporaryDirectory() as td, patch.object(runner,'_new_session',return_value=Driver()), patch.object(runner,'_execute',side_effect=RuntimeError('failed synthetic-inline-secret at synthetic-serial')):
            result=runner.run_scenario('url',{'udid':'synthetic-serial'},'android',{'name':'flow','steps':[{'type':'type_text','text':'synthetic-inline-secret'}]},Path(td))
        self.assertEqual(result['status'],'failed')
        self.assertNotIn('synthetic-inline-secret',json.dumps(result))
        self.assertNotIn('synthetic-serial',json.dumps(result))
    def test_emulator_log_is_private_and_inside_requested_run(self):
        class Process:
            def poll(self): return None
        with tempfile.TemporaryDirectory() as td,patch.object(devices,'sdk_tool',return_value='sdk'),patch.object(devices,'emulator_path',return_value='emu'),patch.object(devices,'adb_path',return_value='adb'),patch.object(devices,'_create_avd'),patch.object(devices,'_delete_avd'),patch.object(devices,'choose_emulator_port',return_value=5554),patch.object(devices,'_adb_serials',return_value={'emulator-5554'}),patch.object(devices.subprocess,'Popen',return_value=Process()),patch.object(devices,'_run',side_effect=lambda args,**kw:'1' if args[-1]=='sys.boot_completed' else '35' if args[-1]=='ro.build.version.sdk' else ''):
            info=devices.prepare_android('35','test-avd',log_root=Path(td)/'private-logs')
            log=Path(info['log'])
            self.assertEqual(log.parent,Path(td)/'private-logs')
            if os.name!='nt': self.assertEqual(log.stat().st_mode & 0o777,0o600)


@unittest.skipUnless(importlib.util.find_spec('appium'), 'Real Appium Python client unavailable')
class RealCapabilitiesTests(unittest.TestCase):
    def test_market_options_never_serialize_an_app_binary(self):
        for platform,runtime in [('android',{'udid':'synthetic','appPackage':'com.app','preinstalled':True,'noReset':True}),('ios',{'udid':'synthetic','bundleId':'com.app','preinstalled':True,'noReset':True})]:
            with self.subTest(platform=platform):
                caps=runner._options(runtime,platform).to_capabilities()
                self.assertNotIn('appium:app',caps)
                self.assertEqual(caps['appium:udid'],'synthetic')
                self.assertTrue(caps['appium:noReset'])
    def test_market_options_reject_supplied_binary(self):
        with self.assertRaises(ValueError):
            runner._options({'udid':'synthetic','preinstalled':True,'appPath':'forbidden.apk'},'android')


if __name__=='__main__': unittest.main()
