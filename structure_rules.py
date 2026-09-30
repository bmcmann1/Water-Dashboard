"""Published USACE floodway design thresholds; NOT an operations telemetry feed.

A below-threshold inference is conditional on a fresh upstream flow and absent
contradictory opening notice. Old River normally diverts water and is NEVER set
closed based on a Morganza/Bonnet Carré threshold.
"""
import datetime as dt

RULES={
 'morganza':{'threshold_cfs':1_500_000,'reference':'https://www.mvn.usace.army.mil/Media/News-Releases/Article/1458246/mississippi-river-flood-fight-operations-update/'},
 'bonnet':{'threshold_cfs':1_250_000,'reference':'https://www.mvd.usace.army.mil/Portals/52/docs/regional_flood_risk_management/Docs/SectionIV-MRTOperation.pdf'}}
OLD_RIVER='https://rivergages.mvr.usace.army.mil/WaterControl/shefdata2.cfm?d=&sid=02600Q'

def infer(flow,structure,notice=None):
    if structure=='oldriver':return {'status':'NORMAL_DIVERSION_EXPECTED','assumed_outflow_cfs':None,'source':OLD_RIVER,'warning':'Do not assume zero outflow; verify total ORCC discharge.'}
    rule=RULES.get(structure)
    if not rule:return {'status':'NO_RULE','assumed_outflow_cfs':None}
    if notice and notice.get('confirmed_open'):
        return {'status':'OPEN_CONFIRMED_BY_NOTICE','assumed_outflow_cfs':None,'source':notice.get('url'),'warning':'News confirms operation, not current discharge.'}
    if not flow or flow.get('cfs') is None:return {'status':'UNKNOWN_NO_FRESH_FLOW','assumed_outflow_cfs':None,'source':rule['reference']}
    try:
        t=dt.datetime.fromisoformat(flow['time'].replace('Z','+00:00'));age=(dt.datetime.now(dt.timezone.utc)-t).total_seconds()/3600
    except (ValueError,KeyError,TypeError):age=1e9
    if age< -2 or age>24:return {'status':'UNKNOWN_STALE_FLOW','assumed_outflow_cfs':None,'source':rule['reference']}
    if flow['cfs']<rule['threshold_cfs']:
        return {'status':'PRESUMED_CLOSED_BELOW_DESIGN_TRIGGER','assumed_outflow_cfs':0,'source':rule['reference'],'warning':'Operational inference only; a current USACE opening notice or telemetry overrides.'}
    return {'status':'OPENING_POSSIBLE_CHECK_USACE','assumed_outflow_cfs':None,'source':rule['reference']}
