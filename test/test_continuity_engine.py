import sys, pathlib, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from continuity import solve
class ContinuityTests(unittest.TestCase):
 def test_verified_inflow_and_residual(self):
  nodes={'a':{'current_discharge':{'cfs':100,'time':'2026-09-29T00:00:00Z'}},'b':{},'c':{'current_discharge':{'cfs':125,'time':'2026-09-29T00:00:00Z'}},'t':{'current_discharge':{'cfs':20,'time':'2026-09-29T00:00:00Z'},'mouth_equivalence_approved':True}}
  r,a=solve(nodes,['a','b','c'],[{'id':'t','parent':'b','kind':'in'}],'2026-09-29T01:00:00Z')
  self.assertEqual(r['b']['cfs'],120);self.assertEqual(r['c']['residual_cfs'],5)
 def test_unapproved_candidate_is_not_added(self):
  nodes={'a':{'current_discharge':{'cfs':100,'time':'2026-09-29T00:00:00Z'}},'b':{},'t':{'current_discharge':{'cfs':20,'time':'2026-09-29T00:00:00Z'}}}
  r,_=solve(nodes,['a','b'],[{'id':'t','parent':'b','kind':'in'}],'2026-09-29T01:00:00Z')
  self.assertIsNone(r['b']['cfs']);self.assertEqual(r['b']['missing'],['t'])
 def test_no_duplicate_upstream(self):
  nodes={'a':{'current_discharge':{'cfs':100,'time':'2026-09-29T00:00:00Z'}},'b':{}}
  r,_=solve(nodes,['a','b'],[],'2026-09-29T01:00:00Z');self.assertEqual(r['b']['cfs'],100)
 def test_stale_rejected(self):
  nodes={'a':{'current_discharge':{'cfs':100,'time':'2026-09-20T00:00:00Z'}},'b':{}}
  r,_=solve(nodes,['a','b'],[],'2026-09-29T01:00:00Z');self.assertIsNone(r['b']['cfs'])
if __name__=='__main__':unittest.main()
