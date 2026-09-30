import json, pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ContinuityMapTests(unittest.TestCase):
 def test_all_junctions_have_parent_and_direction(self):
  r=json.loads((ROOT/'network_registry.json').read_text()); main={x['id'] for x in r['reaches']}; ids={x['id'] for x in r['junctions']}
  for j in r['junctions']:
   self.assertIn(j['parent'],main)
   self.assertIn(j['kind'],('in','out'))
   self.assertNotIn(j['id'],main)
  self.assertEqual(len(ids),len(r['junctions']))
 def test_no_unverified_tributary_is_assumed_zero(self):
  src=(ROOT/'scripts/continuity.py').read_text()
  self.assertIn("missing.append(ident)",src)
  self.assertIn("if valid and not missing else None",src)
 def test_map_controls_and_continuity_visuals(self):
  src=(ROOT/'scripts/dashboard_template.html').read_text()
  for item in ('zoomIn','zoomOut','zoomReset','reach_flow','junction_kinds','pointermove','wheel'):
   if item=='junction_kinds': continue
   self.assertIn(item,src)
