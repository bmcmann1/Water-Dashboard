import datetime as dt,json,pathlib,tempfile,unittest,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from acquire_validated_fallbacks import acquire,candidate_ok
from structure_rules import infer
class FallbackV13(unittest.TestCase):
 def test_river_identity_rejects_nearby_wrong_river(self):
  self.assertFalse(candidate_ok('arkansas','Bayou Bartholomew at Jones'));self.assertTrue(candidate_ok('ohio','Ohio River at Olmsted, IL'))
 def test_fresh_primary_skips_network(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td);(p/'normalized_network.json').write_text(json.dumps({'nodes':{'ohio':{'kind':'tributary','usgs':{'03612600':{'00060':[{'time':dt.datetime.now(dt.timezone.utc).isoformat(),'value':123,'unit':'ft3/s'}]}}}}}))
   result=acquire(p,fetch=lambda _:self.fail('Should not fetch backup when primary is fresh'))
   self.assertEqual(result['nodes']['ohio']['status'],'PRIMARY_AVAILABLE_BACKUP_OPTIONAL')
 def test_old_river_not_assumed_closed(self):self.assertIsNone(infer({'cfs':100,'time':dt.datetime.now(dt.timezone.utc).isoformat()},'oldriver')['assumed_outflow_cfs'])
 def test_morganza_below_threshold_conditional(self):
  v=infer({'cfs':500000,'time':dt.datetime.now(dt.timezone.utc).isoformat()},'morganza');self.assertEqual(v['assumed_outflow_cfs'],0);self.assertIn('PRESUMED',v['status'])
if __name__=='__main__':unittest.main()
