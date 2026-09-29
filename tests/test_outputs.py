import json,pathlib,unittest
P=pathlib.Path
class TestOutputs(unittest.TestCase):
 def test_registry_42(self):
  r=json.loads(P('network_registry.json').read_text());self.assertEqual(len(r['reaches'])+len(r['junctions']),42)
 def test_exact_usace_not_fabricated(self):
  c=json.loads(P('config/usace_series.json').read_text());self.assertEqual(c['series'],[])
 def test_normalized_if_present(self):
  f=P('output/normalized_network.json')
  if not f.exists():self.skipTest('Run acquisition and normalization first')
  d=json.loads(f.read_text());self.assertEqual(len(d['nodes']),42);self.assertEqual(len(d['coverage'])>0,True)
 def test_dashboard_if_present(self):
  f=P('site/index.html')
  if not f.exists():self.skipTest('Run build first')
  h=f.read_text();self.assertIn('id="network-data"',h);self.assertNotIn('__PAYLOAD__',h)
if __name__=='__main__':unittest.main()
