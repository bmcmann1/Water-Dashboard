import importlib.util, pathlib, unittest, tempfile, json
spec=importlib.util.spec_from_file_location('fallback',pathlib.Path('scripts/discover_fallbacks.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TestFallback(unittest.TestCase):
 def test_distance(self):
  self.assertEqual(m.distance_km((-90,30),(-90,30)),0)
  self.assertGreater(m.distance_km((-90,30),(-91,30)),90)
 def test_rdb(self):
  text='# header\nagency_cd\tsite_no\tstation_nm\tdec_lat_va\tdec_long_va\n5s\t15s\t50s\t16s\t16s\nUSGS\t01234567\tTest River\t30.0\t-90.0\n'
  self.assertEqual(m.parse_rdb(text)[0]['site'],'01234567')
 def test_candidate_not_approved(self):
  text=b'agency_cd\tsite_no\tstation_nm\tdec_lat_va\tdec_long_va\n5s\t15s\t50s\t16s\t16s\nUSGS\t01234567\tTest River\t30.0\t-90.0\n'
  rows,log=m.discover('test',(-90,30),set(),fetch=lambda _:text)
  self.assertEqual(rows[0]['approval'],'NOT_APPROVED');self.assertEqual(log['status'],200)
 def test_actionable_when_catalog_fails(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);(root/'complete_verification.json').write_text(json.dumps({'blockers':[{'node':'ohio','variable':'discharge'}]}))
   report=m.plan(root,fetch=lambda _: (_ for _ in ()).throw(OSError('offline')))
   self.assertTrue(report['stations']['ohio']['alternatives'])
if __name__=='__main__':unittest.main()
