import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from continuity import solve
class TestV9(unittest.TestCase):
 def test_zero_valid_lateral(self):
  t='2026-09-30T00:00:00+00:00';nodes={'a':{'current_discharge':{'cfs':100,'time':t}},'b':{},'x':{'current_discharge':{'cfs':0,'time':t},'mouth_equivalence_approved':True}}
  result,audit=solve(nodes,['a','b'],[{'id':'x','parent':'b','kind':'in'}],t)
  self.assertEqual(result['b']['cfs'],100)
  self.assertEqual(result['b']['status'],'continuity')
 def test_unverified_lateral_never_added(self):
  t='2026-09-30T00:00:00+00:00';nodes={'a':{'current_discharge':{'cfs':100,'time':t}},'b':{},'x':{'current_discharge':{'cfs':200,'time':t}}}
  result,_=solve(nodes,['a','b'],[{'id':'x','parent':'b','kind':'in'}],t)
  self.assertIsNone(result['b']['cfs'])
if __name__=='__main__':unittest.main()
