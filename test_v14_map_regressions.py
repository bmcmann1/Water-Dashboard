import pathlib,unittest,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from continuity import solve
class MapRegressionTests(unittest.TestCase):
 def test_partial_keeps_accounted_flow_without_claiming_complete(self):
  nodes={'a':{'current_discharge':{'cfs':100,'time':'2026-09-30T00:00:00Z'}},'b':{},'tributary':{}}
  result,_=solve(nodes,['a','b'],[{'id':'tributary','parent':'b','kind':'in'}],'2026-09-30T00:00:00Z')
  self.assertEqual(result['b']['status'],'partial');self.assertIsNone(result['b']['cfs']);self.assertEqual(result['b']['accounted_cfs'],100)
 def test_map_clicks_not_captured_by_pan(self):
  t=(pathlib.Path(__file__).resolve().parents[1]/'scripts/dashboard_template.html').read_text()
  self.assertIn("e.target.closest('.station')",t);self.assertIn('data-select-node',t);self.assertIn('accounted_cfs',t)
 def test_coverage_provenance_collapsible(self):
  t=(pathlib.Path(__file__).resolve().parents[1]/'scripts/dashboard_template.html').read_text()
  self.assertIn('<details id="coverage-details"><summary>Coverage and provenance</summary><div id="tributary-method" class="muted"></div><div id="coverage"></div></details>',t)
  self.assertIn('<summary>Acquisition diagnostics (all attempted routes)</summary>',t)
