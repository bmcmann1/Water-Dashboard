import json,pathlib,unittest
P=pathlib.Path
class TestOutputs(unittest.TestCase):
 def test_registry_46(self):
  r=json.loads(P('network_registry.json').read_text());self.assertEqual(len(r['reaches'])+len(r['junctions']),46)
 def test_exact_usace_not_fabricated(self):
  c=json.loads(P('config/usace_series.json').read_text());self.assertTrue(all(x.get('approved') and x.get('timeseries_id') for x in c['series'] if x.get('variable') not in ('gate_opening','operation')))
 def test_normalized_if_present(self):
  f=P('output/normalized_network.json')
  if not f.exists():self.skipTest('Run acquisition and normalization first')
  d=json.loads(f.read_text());self.assertEqual(len(d['nodes']),46);self.assertEqual(len(d['coverage'])>0,True)
 def test_dashboard_if_present(self):
  f=P('site/index.html')
  if not f.exists():self.skipTest('Run build first')
  h=f.read_text();self.assertIn('id="network-data"',h);self.assertNotIn('__PAYLOAD__',h)
if __name__=='__main__':unittest.main()
