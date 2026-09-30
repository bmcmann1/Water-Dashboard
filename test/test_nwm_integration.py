"""Guardrails for the optional NWM integration and new tributaries."""
import json, pathlib, unittest
P=pathlib.Path
class NWMGuardrails(unittest.TestCase):
 def test_twenty_tributaries(self):
  r=json.loads(P('network_registry.json').read_text())
  inflows=[n for n in r['junctions'] if n['kind']=='in']
  self.assertEqual(len(inflows),20)
  self.assertEqual(len(r['reaches'])+len(r['junctions']),46)
 def test_all_inflows_have_crosswalk_entries(self):
  r=json.loads(P('network_registry.json').read_text());pairs=json.loads(P('config/nwm_reach_pairs.json').read_text())['pairs']
  self.assertEqual({n['id'] for n in r['junctions'] if n['kind']=='in'},set(pairs))
 def test_unverified_mapping_has_no_reach_id(self):
  pairs=json.loads(P('config/nwm_reach_pairs.json').read_text())['pairs']
  for x in pairs.values():
   for role in ('gauge','mouth'):
    if not x[role+'_match_verified']:self.assertIsNone(x[role+'_reach_id'])
 def test_no_false_observation_claim(self):
  source=P('scripts/normalize_qc.py').read_text()
  self.assertIn("obj['nwm']",source)
  self.assertNotIn("candidates += [('NWM'",source)
if __name__=='__main__':unittest.main()
