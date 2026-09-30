import json,pathlib,unittest
P=pathlib.Path
class Test24hQC(unittest.TestCase):
 def test_normalizer_thresholds(self):
  s=(P('scripts/normalize_qc.py')).read_text()
  self.assertIn('MAX_OBSERVATION_AGE_HOURS=24',s)
  self.assertIn('MAX_NEIGHBOR_GAP_HOURS=24',s)
  self.assertNotIn('BLOCKED_MISSING_LAG_STORAGE_OR_UNCERTAINTY',s)
 def test_output_thresholds_if_present(self):
  f=P('output/qc_report.json')
  if not f.exists():self.skipTest('Acquisition not run')
  q=json.loads(f.read_text())
  self.assertEqual(q['qc_thresholds']['observation_age_hours'],24)
  self.assertEqual(q['qc_thresholds']['neighbor_timestamp_gap_hours'],24)
if __name__=='__main__':unittest.main()
