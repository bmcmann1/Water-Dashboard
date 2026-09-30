#!/usr/bin/env python3
"""Run the unittest suite and write a dashboard-friendly plain-language report."""
import datetime as dt, io, json, pathlib, re, sys, unittest
P=pathlib.Path
DESCRIPTIONS={
'normalizer_thresholds':'Confirms the normalizer uses the agreed 24-hour freshness and time-alignment thresholds.',
'output_thresholds_if_present':'Checks generated QC output preserves those 24-hour thresholds.',
'daily_not_instantaneous':'Prevents daily-average USGS values from being treated as instantaneous discharge.',
'missing_timezone_rejected':'Rejects timestamps that do not identify a timezone.',
'ogc_explicit_parameter':'Requires the USGS OGC response to identify the requested parameter.',
'ogc_unknown_schema_not_verified':'Does not certify an unfamiliar USGS OGC schema as valid data.',
'sentinel_rejected':'Rejects missing-value sentinel numbers such as -9999.',
'zero_is_valid':'Keeps a real zero flow/measurement as valid instead of treating it as missing.',
'no_duplicate_upstream':'Prevents continuity from counting the upstream mainstem flow twice.',
'stale_rejected':'Prevents stale values from entering the continuity solution.',
'unapproved_candidate_is_not_added':'Prevents an unverified tributary fallback gauge from being added to mainstem flow.',
'verified_inflow_and_residual':'Checks an approved tributary is added correctly and the observed residual is calculated.',
'all_junctions_have_parent_and_direction':'Checks every tributary/diversion has a parent mainstem location and in/out direction.',
'map_controls_and_continuity_visuals':'Checks map zoom/pan controls and observed/estimated flow styling are present.',
'no_unverified_tributary_is_assumed_zero':'Confirms missing tributaries remain unknown rather than silently becoming zero.',
'fresh_primary_skips_network':'Avoids unnecessary fallback network calls when fresh primary data already exist.',
'morganza_below_threshold_conditional':'Checks Morganza closure inference is only conditional and threshold-based.',
'old_river_not_assumed_closed':'Prevents Old River from ever being assumed closed simply because operations data are missing.',
'river_identity_rejects_nearby_wrong_river':'Rejects a geographically nearby gauge when it is on the wrong river.',
'actionable_when_catalog_fails':'Produces an actionable fallback record even if station catalog discovery fails.',
'candidate_not_approved':'Ensures a discovered fallback candidate is not automatically approved.',
'distance':'Checks fallback candidate distance calculations.',
'rdb':'Checks parsing of USGS site-catalog RDB text.',
'baselines_do_not_invent_averages':'Prevents the dashboard from inventing long-term average flows.',
'geography_all_46_nodes':'Confirms all 46 configured network nodes have map positions.',
'self_contained_dashboard':'Confirms the built dashboard is a self-contained HTML file.',
'approximate_mouth_never_approves':'Prevents approximate map coordinates from approving an NWM mouth reach.',
'existing_usgs_coordinates_reused':'Reuses already downloaded USGS coordinates instead of making redundant requests.',
'no_network_when_gis_disabled':'Confirms NWM GIS discovery makes no network request when explicitly disabled.',
'all_inflows_have_crosswalk_entries':'Confirms every configured inflow has an NWM crosswalk record.',
'no_false_observation_claim':'Prevents NWM modeled values from being labeled as observations.',
'twenty_tributaries':'Checks the NWM tributary inventory includes all 20 configured tributaries.',
'unverified_mapping_has_no_reach_id':'Prevents unverified NWM reach IDs from being published as approved mappings.',
'align_and_units':'Checks modeled/observed time alignment and discharge unit conversion.',
'bad_units_and_out_of_window':'Rejects unsupported flow units and timestamps outside the matching window.',
'unverified_never_publishes':'Prevents an unverified NWM pairing from being published as usable.',
'dashboard_if_present':'Checks key dashboard safety language when a dashboard has been built.',
'exact_usace_not_fabricated':'Confirms exact USACE series identifiers are configured rather than invented at runtime.',
'normalized_if_present':'Checks normalized output contains the full network when acquisition has run.',
'registry_46':'Confirms the network registry contains the expected 46 nodes.',
'forecast_has_separate_issue_and_horizon':'Keeps forecast issue time separate from forecast valid-time horizon.',
'mappings_are_catalog_exact':'Checks configured USACE mappings came from exact catalog matches.',
'retry_is_present':'Confirms transient web failures have bounded retry logic.',
'actual_normalized_noaa_schema_passes':'Checks a valid normalized NOAA fixture passes the publication gate.',
'bad_dashboard_blocks_deploy':'Blocks publication when the dashboard fails required safety/coverage checks.',
'forecast_cannot_satisfy_observation_gate':'Prevents forecast data from satisfying an observed-data requirement.',
'missing_nodes_blocks_deploy':'Blocks publication if required network nodes are missing.',
'stale_observations_do_not_pass':'Prevents stale observations from satisfying the publication gate.',
'coverage_provenance_collapsible':'Checks Coverage and provenance is a collapsible dashboard section.',
'map_clicks_not_captured_by_pan':'Checks station clicks are not swallowed by SVG pan pointer capture.',
'partial_keeps_accounted_flow_without_claiming_complete':'Allows known partial flow to be drawn without labeling it a complete estimate.',
'unverified_lateral_never_added':'Reconfirms unverified lateral flow is never added by the continuity engine.',
'zero_valid_lateral':'Confirms a verified zero lateral flow remains a valid hydraulic term.',
'white_uses_clarendon_anchor':'Checks White River reconciliation uses measured Clarendon flow as its quantitative anchor when fresh.',
'stage_never_becomes_discharge':'Confirms lower-river stage checkpoints never get converted into discharge.',
'stfrancis_positive_residual':'Checks a positive Helena-to-Mhoon mainstem difference becomes a clearly labeled St. Francis-area residual.',
'stfrancis_negative_residual_not_flow':'Prevents a negative mainstem residual from becoming a negative tributary discharge.',
'meramec_prefers_eureka_observation':'Checks Meramec reconciliation keeps Eureka observed flow primary and uses lower-river evidence as a check.',
'meramec_model_fallback_is_labeled':'Checks modeled St. Louis-to-Herculaneum residual fallback is explicitly labeled modeled.',
'mills_release_parser':'Checks Wilbur D. Mills rows preserve total release and timestamp semantics.'}

def description(test_id):
    name=test_id.rsplit('.',1)[-1]
    name=name[5:] if name.startswith('test_') else name
    return DESCRIPTIONS.get(name,'Checks '+name.replace('_',' ')+'.')

class RecordingResult(unittest.TextTestResult):
    def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
    def startTest(self,test):
        self._started=dt.datetime.now(dt.timezone.utc);super().startTest(test)
    def _row(self,test,status,detail=''):
        elapsed=(dt.datetime.now(dt.timezone.utc)-self._started).total_seconds()
        self.rows.append({'id':test.id(),'plain_language':description(test.id()),'status':status,'detail':detail,'seconds':round(elapsed,4)})
    def addSuccess(self,test):self._row(test,'PASS');super().addSuccess(test)
    def addSkip(self,test,reason):self._row(test,'SKIP',reason);super().addSkip(test,reason)
    def addFailure(self,test,err):self._row(test,'FAIL',self._exc_info_to_string(err,test)[-700:]);super().addFailure(test,err)
    def addError(self,test,err):self._row(test,'ERROR',self._exc_info_to_string(err,test)[-700:]);super().addError(test,err)
    def addExpectedFailure(self,test,err):self._row(test,'EXPECTED_FAIL');super().addExpectedFailure(test,err)
    def addUnexpectedSuccess(self,test):self._row(test,'UNEXPECTED_PASS');super().addUnexpectedSuccess(test)

suite=unittest.defaultTestLoader.discover('tests')
stream=sys.stdout
runner=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=RecordingResult)
res=runner.run(suite)
report={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'total':res.testsRun,'passed':sum(r['status']=='PASS' for r in res.rows),'failed':sum(r['status'] in ('FAIL','ERROR','UNEXPECTED_PASS') for r in res.rows),'skipped':sum(r['status']=='SKIP' for r in res.rows),'tests':res.rows}
P('output').mkdir(exist_ok=True);P('output/test_results.json').write_text(json.dumps(report,indent=2))
print('Wrote output/test_results.json:',report['total'],'tests,',report['failed'],'failures/errors')
sys.exit(0 if res.wasSuccessful() else 1)
