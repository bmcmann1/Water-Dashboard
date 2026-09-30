import json,pathlib,re,unittest
P=pathlib.Path
class GeographicTests(unittest.TestCase):
 def test_geography_all_46_nodes(self):
  g=json.loads(P('config/geography.json').read_text())['positions']
  r=json.loads(P('network_registry.json').read_text())
  self.assertEqual(len(g),46)
  self.assertEqual(set(g),{x['id'] for x in r['reaches']+r['junctions']})
 def test_baselines_do_not_invent_averages(self):
  b=json.loads(P('config/flow_baselines.json').read_text())
  for v in b['baselines'].values():
   self.assertTrue(v['mean_cfs']>0 and v['period'] and v['source'])
 def test_self_contained_dashboard(self):
  p=P('site/index.html')
  if not p.exists():self.skipTest('Build dashboard first')
  s=p.read_text()
  self.assertIn('id="network-data"',s)
  self.assertIn('six-hour ticks',s)
  self.assertIn('Hydraulic QC details',s)
  self.assertNotIn('src="https:',s)
  self.assertNotIn('__PAYLOAD__',s)
  d=json.loads(re.search(r'<script id="network-data" type="application/json">(.*?)</script>',s,re.S).group(1))
  self.assertEqual(len(d['nodes']),46)
  self.assertLess(p.stat().st_size,5_000_000)
