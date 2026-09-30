"""Offline synthetic checks: no network calls and no real flow invented."""
import importlib.util, pathlib, tempfile, json, unittest
P=pathlib.Path('scripts/verify_nwm_pairing.py')
spec=importlib.util.spec_from_file_location('verify_nwm_pairing',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class VerificationTests(unittest.TestCase):
 def test_align_and_units(self):
  o=[{'time':'2026-01-01T00:00:00Z','value':100,'unit':'cfs'},{'time':'2026-01-01T01:00:00Z','value':200,'unit':'cfs'}]
  q=[{'time':'2026-01-01T00:15:00Z','value':3,'unit':'m3/s'},{'time':'2026-01-01T01:15:00Z','value':6,'unit':'m3/s'}]
  paired=m.match(o,q);self.assertEqual(len(paired),2);self.assertAlmostEqual(paired[0][2],105.944,places=2)
  self.assertEqual(m.metrics(paired)['matched_points'],2)
 def test_bad_units_and_out_of_window(self):
  self.assertEqual(m.match([{'time':'2026-01-01T00:00Z','value':2,'unit':'feet'}],[{'time':'2026-01-01T00:00Z','value':2,'unit':'cfs'}]),[])
  self.assertEqual(m.match([{'time':'2026-01-01T00:00:00Z','value':2,'unit':'cfs'}],[{'time':'2026-01-01T03:00:00Z','value':2,'unit':'cfs'}]),[])
 def test_unverified_never_publishes(self):
  with tempfile.TemporaryDirectory() as d:
   r=pathlib.Path(d);(r/'config').mkdir();(r/'output').mkdir()
   (r/'config/nwm_reach_pairs.json').write_text(json.dumps({'pairs':{'white':{'usgs_site':'123','gauge_reach_id':None,'mouth_reach_id':None,'gauge_match_verified':False,'mouth_match_verified':False}}}))
   result=m.run(r)['nodes']['white'];self.assertFalse(result['publishable_model_guidance']);self.assertTrue(result['backwater_review_required']);self.assertFalse(result['auto_bias_correction_applied'])
if __name__=='__main__':unittest.main()
