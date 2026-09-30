import datetime as dt, importlib.util, pathlib, tempfile, json, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('recon',ROOT/'scripts/reconcile_priority_tributaries.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)

class V16ReconciliationTests(unittest.TestCase):
    def setUp(self):
        R.NOW=dt.datetime(2026,9,30,12,tzinfo=dt.timezone.utc)
        R.NET={'nodes':{}}
    def test_stage_never_becomes_discharge(self):
        self.assertIsNone(R.cfs(10,'ft'))
        self.assertEqual(R.cfs(10,'cfs'),10)
    def test_stfrancis_positive_residual(self):
        up=[{'time':'2026-09-30T10:00:00+00:00','cfs':100000,'source':'up','source_class':'modeled'}]
        dn=[{'time':'2026-09-30T10:00:00+00:00','cfs':112000,'source':'dn','source_class':'modeled'}]
        x=R.paired_residual(up,dn);self.assertEqual(x['cfs'],12000);self.assertEqual(x['source_class'],'modeled')
    def test_stfrancis_negative_residual_not_flow(self):
        x=R.result('stfrancis','NONPOSITIVE_RESIDUAL',-5000,usable=False)
        self.assertIsNone(x['cfs']);self.assertFalse(x['usable_for_continuity'])
    def test_meramec_prefers_eureka_observation(self):
        R.NET={'nodes':{'meramec':{'usgs':{'07019000':{'00060':[{'time':'2026-09-30T11:00:00+00:00','value':4321,'unit':'cfs'}]},'07019300':{'00065':[]}}}}}
        old_nwm,old_stage=R.priority_nwm,R.priority_stage
        R.priority_nwm=lambda lid: []
        R.priority_stage=lambda lid: []
        try:
            x=R.meramec();self.assertEqual(x['cfs'],4321);self.assertEqual(x['source_class'],'observed_reconciled')
        finally:R.priority_nwm,R.priority_stage=old_nwm,old_stage
    def test_meramec_model_fallback_is_labeled(self):
        R.NET={'nodes':{'meramec':{'usgs':{'07019000':{'00060':[]},'07019300':{'00065':[]}}}}}
        old_nwm,old_stage=R.priority_nwm,R.priority_stage
        R.priority_stage=lambda lid: []
        R.priority_nwm=lambda lid: ([{'time':'2026-09-30T11:00:00+00:00','cfs':100000,'source':'m','source_class':'modeled'}] if lid=='EADM7' else [{'time':'2026-09-30T11:00:00+00:00','cfs':106000,'source':'m','source_class':'modeled'}] if lid=='HRCM7' else [])
        try:
            x=R.meramec();self.assertEqual(x['cfs'],6000);self.assertEqual(x['source_class'],'modeled_mainstem_residual')
        finally:R.priority_nwm,R.priority_stage=old_nwm,old_stage
    def test_white_uses_clarendon_anchor(self):
        old_load,old_stage,old_nwm=R.load,R.priority_stage,R.priority_nwm
        R.load=lambda path:{'series':[{'time':'2026-09-30T11:00:00+00:00','cfs':12500}]} if str(path).endswith('priority_clarendon.json') else None
        R.priority_stage=lambda lid: []
        R.priority_nwm=lambda lid: []
        try:
            x=R.white();self.assertEqual(x['cfs'],12500);self.assertTrue(x['usable_for_continuity'])
        finally:R.load,R.priority_stage,R.priority_nwm=old_load,old_stage,old_nwm
    def test_mills_release_parser(self):
        src=(ROOT/'scripts/acquire_mills_dam.py').read_text()
        self.assertIn('total_release_cfs',src);self.assertIn("ZoneInfo('America/Chicago')",src)
        build=(ROOT/'scripts/build_dashboard.py').read_text()
        self.assertLess(build.index("compact['tributary_policy']"),build.index('results,audit=solve('))

if __name__=='__main__':unittest.main()
