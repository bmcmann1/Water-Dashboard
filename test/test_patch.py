import unittest, pathlib, json, ast
ROOT=pathlib.Path(__file__).resolve().parents[1]
class PatchTests(unittest.TestCase):
 def test_mappings_are_catalog_exact(self):
  config=json.loads((ROOT/'config/usace_series.json').read_text())
  assert len(config['series'])>=10
  for x in config['series']:
   self.assertTrue(x['approved']);self.assertNotIn(x['variable'],('operation','gate_opening'))
   self.assertTrue(x['timeseries_id']);self.assertTrue(x['office'])
 def test_retry_is_present(self):
  src=(ROOT/'scripts/acquire_usgs_usace.py').read_text()
  self.assertIn('Retry-After',src);self.assertIn('429',src);ast.parse(src)
 def test_forecast_has_separate_issue_and_horizon(self):
  src=(ROOT/'scripts/normalize_qc.py').read_text()
  self.assertIn('forecast_issue_utc',src);self.assertIn('forecast_valid_end_utc',src)
  self.assertIn("x['variable']!='stage_forecast'",src)
  ast.parse(src)
if __name__=='__main__':unittest.main()
