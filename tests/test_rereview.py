"""Regression fixtures for Claude's PR #2 follow-up; no devices or SDK replacements."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from osdiff import crawler, market
from test_review_fixes import Driver, Element, android, button


def field(label="Search places", rid="field", secure="false"):
    return f'<node class="android.widget.EditText" resource-id="{rid}" text="{label}" password="{secure}" enabled="true" bounds="[0,0][20,20]"/>'


class ReplayInputTests(unittest.TestCase):
    def source_and_action(self, input_source=None):
        source=android((input_source if input_source is not None else field())+button("Details",rid="details"))
        action=crawler.discover_actions(source,"android",{})[0][0]
        return source,action

    def replay(self, driver, action, cfg):
        with patch.object(crawler,"_prepare_path",return_value=True), patch.object(crawler,"_find_elements",side_effect=lambda d,l:d.find(l)):
            return crawler.replay_path("url",{"appPackage":"com.app"},"android",[action],dict(cfg,settleSeconds=0),driver=driver)

    def test_unruled_search_does_not_stop_button_replay(self):
        source,action=self.source_and_action()
        driver=Driver(source)
        used,trace,error,reset=self.replay(driver,action,{})
        self.assertIs(used,driver)
        self.assertIsNone(error)
        self.assertEqual(trace[0]["status"],"passed")
        self.assertEqual(trace[0]["blockedInputs"][0]["reason"],"no_auto_input_rule")
        self.assertEqual(driver.elements[-1].clicked,1)
        self.assertFalse(driver.elements[1].typed)

    def test_baseline_explores_child_despite_optional_search_and_stays_partial(self):
        source,_=self.source_and_action(); driver=Driver(source)
        destination=android('<node class="TextView" text="Details"/>')
        def reset(d,*args):
            d.page_source=source; d.elements=[Element(n) for n in ET.fromstring(source).iter()]
            return True
        execute=crawler.execute_action
        def navigate(d,*args):
            execute(d,*args); d.page_source=destination
        with tempfile.TemporaryDirectory() as td, patch.object(crawler,"_new_driver",return_value=driver), patch.object(crawler,"_prepare_path",side_effect=reset), patch.object(crawler,"_find_elements",side_effect=lambda d,l:d.find(l)), patch.object(crawler,"execute_action",side_effect=navigate), patch.object(crawler,"_save_checkpoint"):
            graph=crawler.crawl_baseline("url",{"appPackage":"com.app"},"android",Path(td),{"settleSeconds":0})
        self.assertEqual(graph["discoveredScreens"],2)
        self.assertFalse(graph["replayFailures"])
        self.assertEqual(graph["coverageStatus"],"PARTIAL")
        self.assertTrue(graph["blockedInputs"])
        self.assertEqual(graph["screens"][1]["path"][0]["requiredInputs"],[])

    def test_intermediate_candidate_blocker_is_recorded_after_successful_navigation(self):
        source,action=self.source_and_action(); driver=Driver(source)
        baseline={"screens":[{"checkpoint":"details","path":[action]}],"discoveredScreens":1,"coverageStatus":"COMPLETE_WITHIN_POLICY","deterministicReset":True}
        execute=crawler.execute_action
        def navigate(d,*args):
            execute(d,*args); d.page_source=android('<node class="TextView" text="Details"/>')
        with tempfile.TemporaryDirectory() as td, patch.object(crawler,"_new_driver",return_value=driver), patch.object(crawler,"_prepare_path",return_value=True), patch.object(crawler,"_find_elements",side_effect=lambda d,l:d.find(l)), patch.object(crawler,"execute_action",side_effect=navigate), patch.object(crawler,"_save_checkpoint"):
            result=crawler.replay_candidate_graph("url",{"appPackage":"com.app"},"android",baseline,Path(td),{"settleSeconds":0})
        self.assertEqual(result["reproducedScreens"],1)
        self.assertFalse(result["failedPaths"])
        self.assertTrue(result["blockedInputs"])
        self.assertEqual(crawler.coverage_summary(baseline,result)["coverageStatus"],"PARTIAL")

    def test_failed_baseline_input_prerequisite_stops_replay(self):
        source,action=self.source_and_action(field("Email"))
        action["requiredInputs"]=[{"strategy":"id","value":"field","ordinal":0}]
        driver=Driver(source)
        used,trace,error,_=self.replay(driver,action,{})
        self.assertIsNone(used)
        self.assertTrue(error)
        self.assertTrue(trace[0]["missingRequiredInputs"])
        self.assertEqual(driver.elements[-1].clicked,0)

    def test_vanished_required_field_stops_replay_even_without_blocker_record(self):
        source,action=self.source_and_action("")
        action["requiredInputs"]=[{"strategy":"id","value":"field","ordinal":0}]
        used,trace,error,_=self.replay(Driver(source),action,{})
        self.assertIsNone(used)
        self.assertTrue(trace[0]["missingRequiredInputs"])

    def test_refused_secret_field_stops_replay(self):
        source,action=self.source_and_action(field("PIN"))
        driver=Driver(source)
        used,trace,error,_=self.replay(driver,action,{"autoInputRules":[{"pattern":"PIN","value":"synthetic-secret","secret":True}]})
        self.assertIsNone(used)
        self.assertTrue(trace[0]["blockedInputs"][0]["requiredForReplay"])
        self.assertFalse(driver.elements[1].typed)
        self.assertEqual(driver.elements[-1].clicked,0)

    def test_required_input_success_replays_and_uses_stable_identity(self):
        source,action=self.source_and_action(field("Email"))
        action["requiredInputs"]=[{"strategy":"id","value":"field","ordinal":0}]
        driver=Driver(source)
        used,trace,error,_=self.replay(driver,action,{"autoInputRules":[{"pattern":"Email","value":"synthetic-user"}]})
        self.assertIs(used,driver)
        self.assertFalse(trace[0]["missingRequiredInputs"])
        self.assertEqual(driver.elements[1].typed,["synthetic-user"])

    def test_baseline_records_filled_input_requirements_without_values(self):
        source,_=self.source_and_action(field("Email")); driver=Driver(source)
        destination=android('<node class="TextView" text="Details"/>')
        def reset(d,*args):
            d.page_source=source; d.elements=[Element(n) for n in ET.fromstring(source).iter()]
            return True
        execute=crawler.execute_action
        def navigate(d,*args):
            execute(d,*args); d.page_source=destination
        with tempfile.TemporaryDirectory() as td, patch.object(crawler,"_new_driver",return_value=driver), patch.object(crawler,"_prepare_path",side_effect=reset), patch.object(crawler,"_find_elements",side_effect=lambda d,l:d.find(l)), patch.object(crawler,"execute_action",side_effect=navigate), patch.object(crawler,"_save_checkpoint"):
            graph=crawler.crawl_baseline("url",{"appPackage":"com.app"},"android",Path(td),{"settleSeconds":0,"afterInputSettleSeconds":0,"autoInputRules":[{"pattern":"Email","value":"synthetic-user"}]})
        action=graph['screens'][1]['path'][0]
        self.assertEqual(action['requiredInputs'],[{'strategy':'id','value':'field','ordinal':0}])
        self.assertNotIn('synthetic-user',json.dumps(action))

    def test_unruled_native_secure_field_is_required_and_stops_replay(self):
        source,action=self.source_and_action(field("Unknown",secure="true"))
        used,trace,error,_=self.replay(Driver(source),action,{})
        self.assertIsNone(used)
        self.assertTrue(trace[0]['blockedInputs'][0]['requiredForReplay'])


class HardwareOsTests(unittest.TestCase):
    def pair(self, manufacturer="Samsung", models=("S23","S24"), builds=("S911BXXS3BXA1","S921BXXU1AXB4")):
        baseline={"deviceId":"synthetic-A","physicalDevice":True,"platform":"android","manufacturer":manufacturer,"model":models[0],"modelVerified":True,"osVersion":"14","apiLevel":"34","securityPatch":"2026-09-01","buildId":"UP1A.231005.007","buildIncremental":builds[0],"appId":"com.app","appVersion":"1","appBuild":"10","marketOriginVerified":True}
        return baseline,dict(baseline,deviceId="synthetic-B",model=models[1],buildIncremental=builds[1])

    def test_samsung_model_specific_incrementals_do_not_qualify(self):
        result=market.validate_market_pair(*self.pair())
        self.assertFalse(result["valid"])
        self.assertEqual(result["osDifferenceFields"],["osVersion","apiLevel","securityPatch"])
        self.assertFalse(result["osDifferenceEvidence"])

    def test_pixel_model_specific_build_suffixes_do_not_qualify(self):
        baseline,candidate=self.pair("Google",("Pixel 7","Pixel 8"),("123","123"))
        baseline["buildId"]="AP2A.240905.003.A1"; candidate["buildId"]="AP2A.240905.003.F1"
        self.assertFalse(market.validate_market_pair(baseline,candidate)["valid"])

    def test_same_verified_model_incremental_qualifies(self):
        baseline,candidate=self.pair(models=("S23","S23"))
        result=market.validate_market_pair(baseline,candidate)
        self.assertTrue(result["valid"])
        self.assertEqual(result["osDifferenceEvidence"][0]["field"],"buildIncremental")

    def test_unverified_or_unknown_models_cannot_qualify_on_build(self):
        for override in ({"modelVerified":False},{"model":None},{"model":"unknown"},{"manufacturer":None},{"model":"iPhone"}):
            with self.subTest(override=override):
                baseline,candidate=self.pair(models=("S23","S23"))
                candidate.update(override)
                self.assertFalse(market.validate_market_pair(baseline,candidate)["valid"])

    def test_different_models_with_known_patch_difference_still_qualify(self):
        baseline,candidate=self.pair(); candidate["securityPatch"]="2026-10-01"
        result=market.validate_market_pair(baseline,candidate)
        self.assertTrue(result["valid"])
        self.assertEqual(result["osDifferenceEvidence"][0]["field"],"securityPatch")


class NavigationPolicyTests(unittest.TestCase):
    def config(self):
        return json.loads((Path(__file__).resolve().parents[1]/"config/local-config.json").read_text(encoding="utf-8"))["crawler"]

    def test_review_label_tradeoffs_are_explicit_with_shipped_policy(self):
        allowed=("Order history","Sort order","In order to continue","Last updated 2 min ago","Updates","Recently removed","Continue","Next","Not now","Settings","Get started")
        # Hardware surfaces and state mutations remain conservative business boundaries.
        blocked=("Connected devices","Remove from favourites","Print preview","Printer status","Place order","Order now","Order","Update now","Delete account")
        for expected,labels in ((False,allowed),(True,blocked)):
            for label in labels:
                with self.subTest(label=label):
                    self.assertEqual(crawler._danger_reason(label,self.config()) is not None,expected)

    def test_status_descendants_allow_card_navigation_but_order_imperative_blocks(self):
        for caption, expected in (("Last updated 2 min ago",True),("Recently removed",True),("Order history",True),("Order",False),("Place order",False)):
            with self.subTest(caption=caption):
                source=android(button("Details",child=f'<node text="{caption}"/>'))
                actions,blocked,_=crawler.discover_actions(source,"android",self.config())
                self.assertEqual(bool(actions),expected)

    def test_live_order_caption_blocks_even_after_safe_source_snapshot(self):
        source=android(button("Details")); driver=Driver(source)
        action=crawler.discover_actions(source,"android",self.config())[0][0]
        ET.SubElement(driver.elements[-1].node,"node",text="Order")
        with patch.object(crawler,"_find_elements",side_effect=lambda d,l:d.find(l)):
            with self.assertRaises(RuntimeError): crawler._tap(driver,"android",action,self.config())
        self.assertEqual(driver.elements[-1].clicked,0)

    def test_custom_broad_noun_rule_is_optional_but_imperatives_cannot_be_removed(self):
        self.assertIsNone(crawler._danger_reason("Order history",{"denyKeywords":[]}))
        self.assertIsNotNone(crawler._danger_reason("Order history",{"denyKeywords":[r"\border\b"],"allowKeywords":["history"]}))
        for label in ("Order","Order now","Pair","Print","Connect","Delete","Remove","Update now"):
            with self.subTest(label=label):
                self.assertIsNotNone(crawler._danger_reason(label,{"denyKeywords":[]}))


if __name__ == "__main__": unittest.main()
