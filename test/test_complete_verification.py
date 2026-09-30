import sys,unittest,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from complete_verification import number,time_utc,usgs_points,ogc_inspect
class VerificationTests(unittest.TestCase):
 def test_zero_is_valid(self):self.assertEqual(number('0'),0.0)
 def test_sentinel_rejected(self):self.assertIsNone(number('-999999'))
 def test_missing_timezone_rejected(self):self.assertIsNone(time_utc('2026-09-29T12:00:00'))
 def test_ogc_unknown_schema_not_verified(self):
  self.assertFalse(ogc_inspect({'features':[{'properties':{'other':3}}]},'00060')['observation_schema_verified'])
 def test_ogc_explicit_parameter(self):
  self.assertTrue(ogc_inspect({'features':[{'properties':{'parameter_code':'00060','time':'2026-09-29T12:00:00Z','value':0}}]},'00060')['observation_schema_verified'])
 def test_daily_not_instantaneous(self):
  self.assertEqual(usgs_points({'value':{'timeSeries':[]}},'00060'),[])
if __name__=='__main__':unittest.main()
