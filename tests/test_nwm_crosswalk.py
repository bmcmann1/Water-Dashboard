"""Offline crosswalk tests: reuse USGS metadata; never approve GIS proximity."""
import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('crosswalk',ROOT/'scripts/discover_nwm_reaches.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class TestCrosswalk(unittest.TestCase):
 def test_existing_usgs_coordinates_reused(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=pathlib.Path(tmp)/'05514500';d.mkdir()
   (d/'00060_legacy.json').write_text(json.dumps({'value':{'timeSeries':[{'sourceInfo':{'siteCode':[{'value':'05514500'}],'siteName':'Cuivre','geoLocation':{'geogLocation':{'longitude':-90.9,'latitude':39.0}}}}]}}))
   self.assertEqual(mod.existing_usgs_metadata('05514500',pathlib.Path(tmp))['lon'],-90.9)
 def test_approximate_mouth_never_approves(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=pathlib.Path(tmp);cfg=d/'pairs.json';cfg.write_text(json.dumps({'pairs':{'cuivre':{'usgs_site':'05514500'}}}))
   geo=d/'geo.json';geo.write_text(json.dumps({'positions':{'cuivre':[-90.64,39.02]}}))
   with patch.object(mod,'spatial_query',return_value=([{'reach_id':'123','attributes':{},'geometry':{}}],'Candidate search succeeded')), patch.object(mod,'request',return_value=None):
    result=mod.run(cfg,d/'out',enable_gis=True,raw_dir=d/'empty',geography=geo)
   self.assertFalse(result['nodes']['cuivre']['mouth_verified'])
   self.assertEqual(result['nodes']['cuivre']['mouth_coordinate_status'],'approximate map location: discovery ONLY')
 def test_no_network_when_gis_disabled(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=pathlib.Path(tmp);cfg=d/'pairs.json';cfg.write_text(json.dumps({'pairs':{'example':{'usgs_site':None}}}))
   r=mod.run(cfg,d/'out',raw_dir=d/'empty',geography=d/'missing')
   self.assertEqual(r['requests'],[])
if __name__=='__main__':unittest.main()
