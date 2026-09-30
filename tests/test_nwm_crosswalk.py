"""Offline tests: identity guard, safe no-op and bounded audit outputs."""
import importlib.util, json, pathlib, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('crosswalk',ROOT/'scripts/discover_nwm_reaches.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class TestCrosswalk(unittest.TestCase):
    def test_identity_guard(self):
        self.assertEqual(mod.gauge_match({'usgsId':'05514500','reachId':'123'},'05514500')[0],'123')
        self.assertIsNone(mod.gauge_match({'usgsId':'99999999','reachId':'123'},'05514500')[0])
    def test_no_gauge_no_network_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=pathlib.Path(tmp)/'pairs.json';config.write_text(json.dumps({'pairs':{'example':{'usgs_site':None}}}))
            result=mod.run(config,pathlib.Path(tmp)/'out')
            self.assertEqual(result['requests'],[])
            self.assertFalse(result['nodes']['example']['gauge_verified'])
            self.assertTrue((pathlib.Path(tmp)/'out/nwm_crosswalk_review.csv').exists())
if __name__=='__main__':unittest.main()
