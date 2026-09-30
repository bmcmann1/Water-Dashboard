#!/usr/bin/env python3
"""Normalize verifiable readings; preserve provenance and never infer missing flow."""
import csv,datetime as dt,json,math,pathlib,statistics
P=pathlib.Path; ROOT=P('output'); ROOT.mkdir(exist_ok=True); REG=json.loads(P('network_registry.json').read_text()); PRIORITY=json.loads(P('config/priority_tributary_policy.json').read_text())['rivers']; NODES=REG['reaches']+REG['junctions']; NOW=dt.datetime.now(dt.timezone.utc); MAX_OBSERVATION_AGE_HOURS=24; MAX_NEIGHBOR_GAP_HOURS=24

def load(path):
 try:return json.loads(P(path).read_text())
 except (OSError,ValueError):return None

def timeparse(s):
 try:
  t=dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
  return t.astimezone(dt.timezone.utc) if t.tzinfo else None
 except (ValueError,TypeError,OverflowError):return None

def valid(v):
 try:
  n=float(v)
  return n if math.isfinite(n) and n not in (-999,-9999,-99999,9999,99999) else None
 except (ValueError,TypeError):return None

def usgs_legacy(site,code):
 obj=load(ROOT/'raw/usgs'/site/(code+'_legacy.json'));out=[]
 if not isinstance(obj,dict):return out
 for ts in obj.get('value',{}).get('timeSeries',[]):
  variable=ts.get('variable',{});units=(variable.get('unit') or {}).get('unitCode')
  for block in ts.get('values',[]):
   for v in block.get('value',[]):
    t=timeparse(v.get('dateTime'));n=valid(v.get('value'))
    if t and n is not None:out.append({'time':t.isoformat(),'value':n,'unit':units,'qualifiers':v.get('qualifiers',[]),'source':'USGS legacy IV','site':site,'parameter':code})
 return list({p['time']:p for p in sorted(out,key=lambda x:x['time'])}.values())

def noaa_series(lid,section):
 obj=load(ROOT/'raw/nwps'/lid/'stageflow.json');data=(obj.get(section) or {}).get('data',[]) if isinstance(obj,dict) else [];out=[]
 for v in data:
  if not isinstance(v,dict):continue
  t=timeparse(v.get('validTime'));n=valid(v.get('primary'))
  if t and n is not None and -100<n<2000:out.append({'time':t.isoformat(),'value':n,'unit':'ft (native stage; check NOAA metadata)','source':'NOAA NWPS '+section,'site':lid})
 return list({p['time']:p for p in sorted(out,key=lambda x:x['time'])}.values())

def cwms_series(node,variable):
 obj=load(ROOT/'raw/usace/series'/node/(variable+'.json')); mapping=load(ROOT/'raw/usace/series'/node/(variable+'.mapping.json'));out=[]
 if not isinstance(obj,dict) or not isinstance(mapping,dict):return out
 for v in obj.get('values',[]):
  if not isinstance(v,list) or len(v)<2:continue
  t=timeparse(dt.datetime.fromtimestamp(v[0]/1000,dt.timezone.utc).isoformat()) if isinstance(v[0],(int,float)) else timeparse(v[0]);n=valid(v[1])
  if t and n is not None:out.append({'time':t.isoformat(),'value':n,'unit':obj.get('units') or mapping['unit'],'source':'USACE CWMS exact approved ID','site':mapping['timeseries_id'],'quality_code':v[2] if len(v)>2 else None})
 return sorted(out,key=lambda x:x['time'])

# All network entries, including those with no current telemetry, are retained.
ref={'illinois':['05587060'],'missouri':['06935965'],'meramec':['07019130'],'kaskaskia':['05595000'],'bigmuddy':['05599500'],'hatchie':['07029500'],'loosahatchie':['07030357','07030240'],'wolf':['07031740','07031650'],'stfrancis':[],'white':['07077830'],'arkansas':['07265280'],'yazoo':['07288800'],'bigblack':['07290000'],'homochitto':['07292500'],'bayousara':['07373300'],'lafourche':['07380401'],'davis':['295501090190400'],'caernarvon':['295124089542100'],'bellechasse':['07374525'],'baton':['07374000'],'natchez':['07290880'],'vicksburg':['07289000'],'thebes':['07022000'],'stlouis':['07010000'],'grafton':['05587450'],'cuivre':['05514500'],'obion':['07026040'],'salt':[],'forkeddeer':[]}
candidate_nodes=(load('config/tributary_candidates.json') or {}).get('nodes',{})
rows=[];normalized={};missing=[]
for n in NODES:
 lid=n.get('lid');node=n['id'];sites=list(dict.fromkeys(([str(n['usgs'])] if n.get('usgs') else [])+ref.get(node,[])+PRIORITY.get(node,{}).get('usgs_flow',[])+PRIORITY.get(node,{}).get('usgs_stage',[])+candidate_nodes.get(node,{}).get('usgs_sites',[])))
 obj={'id':node,'name':n['name'],'kind':n.get('kind'),'noaa_lid':lid or None,'usgs_candidates':sites,'noaa':{},'usgs':{},'usace':{},'nwm':{},'caveats':[]}
 if lid:
  for section in ('observed','forecast'):
   arr=noaa_series(lid,section);obj['noaa'][section]=arr
  obj['noaa']['metadata_available']=load(ROOT/'raw/nwps'/lid/'metadata.json') is not None
  obj['noaa']['ratings_available']=load(ROOT/'raw/nwps'/lid/'ratings.json') is not None
  obj['noaa']['hefs_parameters']=[f.stem.removeprefix('quantiles_') for f in (ROOT/'raw/hefs'/lid).glob('quantiles_*.json')] if (ROOT/'raw/hefs'/lid).exists() else []
 for site in sites:
  obj['usgs'][site]={code:usgs_legacy(site,code) for code in ('00060','00065','63160')}
 # Model output is a separate product. It must never satisfy observation freshness QC.
 model=load(ROOT/'nwm_normalized.json') or {}
 obj['nwm']=model.get('nodes',{}).get(node,{})
 pairing=load(ROOT/'nwm_pairing_verification.json') or {}
 obj['nwm_verification']=pairing.get('nodes',{}).get(node,{})
 for variable in ('discharge','stage','water_surface_elevation','gate_opening','operation'):
  arr=cwms_series(node,variable)
  if arr:obj['usace'][variable]=arr
 if node=='cairo' or node=='ohio':obj['caveats'].append('CIRI2 is Ohio River stage; do not treat as Mississippi downstream discharge.')
 if n['kind']!='mainstem':obj['caveats'].append('Upstream reference gauge values are not confluence water-surface elevations.')
 if node=='natchez':obj['caveats'].append('17.28 ft NGVD29 zero documented; regional NAVD88 estimate is provisional, not a certified conversion.')
 normalized[node]=obj
 for source,station,variable,arr in [('NOAA',lid,'stage_observed',obj['noaa'].get('observed',[])),('NOAA',lid,'stage_forecast',obj['noaa'].get('forecast',[]))]+[( 'USGS',site,code,series) for site,ss in obj['usgs'].items() for code,series in ss.items()]+[('USACE',node,k,v) for k,v in obj['usace'].items()]:
  last=arr[-1]['time'] if arr else None
  if variable=='stage_forecast':
   meta=load(ROOT/'raw/nwps'/lid/'stageflow.json') if lid else None
   # Forecast valid times can lie in the future. Their maximum is a horizon, not an issue timestamp.
   issue_candidates=[]
   if isinstance(meta,dict):
    def scan_issue(v,depth=0):
     if depth>3:return
     if isinstance(v,dict):
      for k,x in v.items():
       if k.lower() in ('issuetime','issuedtime','issuedat','forecastissuetime','generationtime','generatedat'):
        t=timeparse(x)
        if t:issue_candidates.append(t)
       elif isinstance(x,(dict,list)):scan_issue(x,depth+1)
     elif isinstance(v,list):
      for x in v[:3]:scan_issue(x,depth+1)
    scan_issue(meta)
   issue=max(issue_candidates).isoformat() if issue_candidates else None
   age=(NOW-timeparse(issue)).total_seconds()/3600 if issue else None
   fresh=age is not None and -2<=age<=72
   status='FORECAST_ISSUE_FRESH' if fresh else 'FORECAST_ISSUE_STALE' if issue else 'FORECAST_ISSUE_UNKNOWN' if arr else 'NOT_RETRIEVED'
   rows.append({'node':node,'name':n['name'],'source':source,'station':station,'variable':variable,'count':len(arr),'latest_utc':last,'age_hours':round(age,2) if age is not None else None,'fresh_24h':False,'status':status,'forecast_issue_utc':issue,'forecast_valid_end_utc':last})
  else:
   # Observation freshness is based on measurement time, NEVER retrieval time.
   age=(NOW-timeparse(last)).total_seconds()/3600 if last else None
   fresh=age is not None and -2<=age<=MAX_OBSERVATION_AGE_HOURS
   rows.append({'node':node,'name':n['name'],'source':source,'station':station,'variable':variable,'count':len(arr),'latest_utc':last,'age_hours':round(age,2) if age is not None else None,'fresh_24h':fresh,'status':'FRESH' if fresh else 'STALE_EXCLUDED_FROM_CURRENT_PROFILE' if arr else 'NOT_RETRIEVED','forecast_issue_utc':None,'forecast_valid_end_utc':None})
 if not any(x['node']==node and x.get('fresh_24h',False) and x['variable']!='stage_forecast' for x in rows):missing.append(node)

# Timestamp-matched NOAA/USGS native-stage comparison: same zero NOT assumed, differences diagnostic only.
cross=[]
for node,obj in normalized.items():
 noaa=obj['noaa'].get('observed',[])
 if not noaa:continue
 for sid,series in obj['usgs'].items():
  stage=series['00065'];pairs=[]
  for a in noaa:
   t=timeparse(a['time']);nearest=min(stage,key=lambda x:abs((timeparse(x['time'])-t).total_seconds()),default=None)
   if nearest and abs((timeparse(nearest['time'])-t).total_seconds())<=1800:pairs.append(a['value']-nearest['value'])
  if pairs:cross.append({'node':node,'usgs_site':sid,'paired_points':len(pairs),'median_native_stage_difference_ft':round(statistics.median(pairs),3),'certified_same_zero':False,'warning':'Diagnostic only; investigate sensor reference and offset before comparing WSE.'})

# Simple contemporary-observation QC: no routing, lag or storage model.
# A warning is diagnostic, not proof of a hydraulic impossibility.
DATUM={r['node_id']:r for r in csv.DictReader(P('config/datum_registry.csv').open(newline=''))}
MAIN=[n['id'] for n in REG['reaches'] if n.get('kind')=='mainstem']
# Cairo is an Ohio River stage station and cannot be a Mississippi mainstem slope endpoint.
MAIN=[x for x in MAIN if x!='cairo']
# Only compare adjacent entries within a continuous mainstem section; never jump across Cairo.
SEGMENTS=[]
for segment in (MAIN[:MAIN.index('thebes')+1],MAIN[MAIN.index('newmadrid'):]):
 SEGMENTS.extend(zip(segment,segment[1:]))

def current(arr):
 return [v for v in arr if (t:=timeparse(v['time'])) and -2<=(NOW-t).total_seconds()/3600<=MAX_OBSERVATION_AGE_HOURS]
def pick(node,kind):
 o=normalized[node]; candidates=[]
 if kind=='stage':
  candidates += [('NOAA',o['noaa'].get('observed',[]))]
  candidates += [('USACE',o['usace'].get('stage',[]))]
  candidates += [('USGS',v.get('00065',[])) for v in o['usgs'].values()]
 elif kind=='discharge':
  candidates += [('USACE',o['usace'].get('discharge',[]))]
  candidates += [('USGS',v.get('00060',[])) for v in o['usgs'].values()]
 # prefer freshest contemporary observation, retain provenance
 opts=[(timeparse(v['time']),src,v) for src,arr in candidates for v in current(arr)]
 return max(opts,key=lambda x:x[0]) if opts else None

def cfs(value,unit):
 u=str(unit or '').lower().replace(' ','')
 if u in ('ft3/s','ft^3/s','cfs','ft³/s'):return value
 if u in ('m3/s','cms','m³/s'):return value*35.3146667
 return None

def navd88_zero(node,source):
 if source!='NOAA':return None # Never apply NOAA zero to USGS/USACE sensor.
 r=DATUM.get(node,{})
 for key in ('NOAA_NAVD88_zero_ft','USACE_NAVD88_adjustment_ft'):
  # USACE adjustment is not interchangeable with NOAA zero; skip it here.
  if key!='NOAA_NAVD88_zero_ft':continue
  try:return float(r[key])
  except (ValueError,KeyError,TypeError):pass
 return None

plausibility=[]
for up,dn in SEGMENTS:
 for kind in ('stage','discharge'):
  a=pick(up,kind);b=pick(dn,kind)
  row={'upstream':up,'downstream':dn,'variable':kind,'max_observation_age_hours':24,'max_neighbor_gap_hours':24}
  if not a or not b:
   row.update(status='INDETERMINATE_MISSING_OR_STALE',reason='No contemporary observations at both endpoints');plausibility.append(row);continue
  ta,sa,va=a;tb,sb,vb=b;gap=abs((ta-tb).total_seconds())/3600
  row.update(upstream_time_utc=ta.isoformat(),downstream_time_utc=tb.isoformat(),timestamp_gap_hours=round(gap,2),upstream_source=sa,downstream_source=sb)
  if gap>MAX_NEIGHBOR_GAP_HOURS:
   row.update(status='INDETERMINATE_TIME_MISMATCH',reason='Observation timestamps differ by over 24 hours');plausibility.append(row);continue
  if kind=='stage':
   za=navd88_zero(up,sa);zb=navd88_zero(dn,sb)
   if za is None or zb is None:
    row.update(status='INDETERMINATE_DATUM',reason='No compatible verified NOAA NAVD88 zeros for both selected series');plausibility.append(row);continue
   hu=va['value']+za;hd=vb['value']+zb
   row.update(upstream_wse_ft=round(hu,3),downstream_wse_ft=round(hd,3),difference_ft=round(hu-hd,3))
   row['status']='REVIEW_DOWNSTREAM_HIGHER' if hd>hu+0.5 else 'PASS'
   row['reason']='0.5 ft screening tolerance; possible backwater, tidal effect or datum error' if row['status'].startswith('REVIEW') else 'Screening-only WSE ordering'
  else:
   qu=cfs(va['value'],va.get('unit'));qd=cfs(vb['value'],vb.get('unit'))
   if qu is None or qd is None:
    row.update(status='INDETERMINATE_UNITS',reason='Discharge units not verified');plausibility.append(row);continue
   row.update(upstream_cfs=round(qu),downstream_cfs=round(qd),ratio_down_up=round(qd/qu,3) if qu>0 else None)
   # Without complete intervening tributary/diversion flow, avoid a false pass/fail.
   if qu>0 and (qd<0.7*qu or qd>1.5*qu):row.update(status='REVIEW_FLOW_DISCREPANCY',reason='Large difference; inspect intervening inflows/outlets, station identity and timestamps')
   else:row.update(status='PASS_SCREEN',reason='No large flow discrepancy; does not establish reach mass balance')
  plausibility.append(row)

balances=[] # Retained only for compatibility with earlier offline dashboard.
out={'generated_utc':NOW.isoformat(),'nodes':normalized,'coverage':rows,'stage_crosschecks':cross,'mass_balance':balances,'plausibility_checks':plausibility,'qc_thresholds':{'observation_age_hours':24,'neighbor_timestamp_gap_hours':24},'notes':['No NOAA stage-to-discharge conversion inferred.','NOAA primary assumed native stage only; NOAA secondary discharge retained in raw stageflow until field/units validation.','USGS OGC routes retained raw; legacy IV used for normalized values until OGC schema is verified against actual GitHub results.','CWMS station series acquired from reviewed exact IDs where available; structural operations intentionally excluded pending threshold gating.','Simple contemporary data-screening checks only; no routing model or certified mass balance.']}
(ROOT/'normalized_network.json').write_text(json.dumps(out,separators=(',',':')))
with (ROOT/'station_coverage.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(ROOT/'qc_report.json').write_text(json.dumps({'generated_utc':NOW.isoformat(),'node_count':len(normalized),'expected_node_count':len(NODES),'nodes_without_fresh_observation':missing,'stage_crosschecks':cross,'mass_balance':balances,'plausibility_checks':plausibility,'qc_thresholds':{'observation_age_hours':24,'neighbor_timestamp_gap_hours':24},'coverage_counts':{'fresh_observation_rows':sum(r.get('fresh_24h',False) for r in rows),'total':len(rows)},'caveats':out['notes']},indent=2))
print('Normalized',len(normalized),'nodes; fresh source/variable rows',sum(r.get('fresh_24h',False) for r in rows),'/',len(rows),'nodes without fresh observation',len(missing))
if len(normalized)!=len(NODES):raise SystemExit('Network coverage registry mismatch')
