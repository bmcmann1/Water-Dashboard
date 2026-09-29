#!/usr/bin/env python3
"""Normalize verifiable readings; preserve provenance and never infer missing flow."""
import csv,datetime as dt,json,math,pathlib,statistics
P=pathlib.Path; ROOT=P('output'); ROOT.mkdir(exist_ok=True); REG=json.loads(P('network_registry.json').read_text()); NODES=REG['reaches']+REG['junctions']; NOW=dt.datetime.now(dt.timezone.utc)

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
 return sorted(out,key=lambda x:x['time'])

def noaa_series(lid,section):
 obj=load(ROOT/'raw/nwps'/lid/'stageflow.json');data=(obj.get(section) or {}).get('data',[]) if isinstance(obj,dict) else [];out=[]
 for v in data:
  if not isinstance(v,dict):continue
  t=timeparse(v.get('validTime'));n=valid(v.get('primary'))
  if t and n is not None and -100<n<2000:out.append({'time':t.isoformat(),'value':n,'unit':'ft (native stage; check NOAA metadata)','source':'NOAA NWPS '+section,'site':lid})
 return sorted(out,key=lambda x:x['time'])

def cwms_series(node,variable):
 obj=load(ROOT/'raw/usace/series'/node/(variable+'.json')); mapping=load(ROOT/'raw/usace/series'/node/(variable+'.mapping.json'));out=[]
 if not isinstance(obj,dict) or not isinstance(mapping,dict):return out
 for v in obj.get('values',[]):
  if not isinstance(v,list) or len(v)<2:continue
  t=timeparse(dt.datetime.fromtimestamp(v[0]/1000,dt.timezone.utc).isoformat()) if isinstance(v[0],(int,float)) else timeparse(v[0]);n=valid(v[1])
  if t and n is not None:out.append({'time':t.isoformat(),'value':n,'unit':obj.get('units') or mapping['unit'],'source':'USACE CWMS exact approved ID','site':mapping['timeseries_id'],'quality_code':v[2] if len(v)>2 else None})
 return sorted(out,key=lambda x:x['time'])

# All network entries, including those with no current telemetry, are retained.
ref={'illinois':['05587060'],'missouri':['06935965'],'meramec':['07019130'],'kaskaskia':['05595000'],'bigmuddy':['05599500'],'hatchie':['07029500'],'loosahatchie':['07030357','07030240'],'wolf':['07031740','07031650'],'stfrancis':[],'white':['07077830'],'arkansas':['07265280'],'yazoo':['07288800'],'bigblack':['07290000'],'homochitto':['07292500'],'bayousara':['07373300'],'lafourche':['07380401'],'davis':['295501090190400'],'caernarvon':['295124089542100'],'bellechasse':['07374525'],'baton':['07374000'],'natchez':['07290880'],'vicksburg':['07289000'],'thebes':['07022000'],'stlouis':['07010000'],'grafton':['05587450']}
rows=[];normalized={};missing=[]
for n in NODES:
 lid=n.get('lid');node=n['id'];sites=list(dict.fromkeys(([str(n['usgs'])] if n.get('usgs') else [])+ref.get(node,[])))
 obj={'id':node,'name':n['name'],'kind':n.get('kind'),'noaa_lid':lid or None,'usgs_candidates':sites,'noaa':{},'usgs':{},'usace':{},'caveats':[]}
 if lid:
  for section in ('observed','forecast'):
   arr=noaa_series(lid,section);obj['noaa'][section]=arr
  obj['noaa']['metadata_available']=load(ROOT/'raw/nwps'/lid/'metadata.json') is not None
  obj['noaa']['ratings_available']=load(ROOT/'raw/nwps'/lid/'ratings.json') is not None
  obj['noaa']['hefs_parameters']=[f.stem.removeprefix('quantiles_') for f in (ROOT/'raw/hefs'/lid).glob('quantiles_*.json')] if (ROOT/'raw/hefs'/lid).exists() else []
 for site in sites:
  obj['usgs'][site]={code:usgs_legacy(site,code) for code in ('00060','00065','63160')}
 for variable in ('discharge','stage','water_surface_elevation','gate_opening','operation'):
  arr=cwms_series(node,variable)
  if arr:obj['usace'][variable]=arr
 if node=='cairo' or node=='ohio':obj['caveats'].append('CIRI2 is Ohio River stage; do not treat as Mississippi downstream discharge.')
 if n['kind']!='mainstem':obj['caveats'].append('Upstream reference gauge values are not confluence water-surface elevations.')
 if node=='natchez':obj['caveats'].append('17.28 ft NGVD29 zero documented; regional NAVD88 estimate is provisional, not a certified conversion.')
 normalized[node]=obj
 for source,station,variable,arr in [('NOAA',lid,'stage_observed',obj['noaa'].get('observed',[])),('NOAA',lid,'stage_forecast',obj['noaa'].get('forecast',[]))]+[( 'USGS',site,code,series) for site,ss in obj['usgs'].items() for code,series in ss.items()]+[('USACE',node,k,v) for k,v in obj['usace'].items()]:
  last=arr[-1]['time'] if arr else None;age=(NOW-timeparse(last)).total_seconds()/3600 if last else None
  rows.append({'node':node,'name':n['name'],'source':source,'station':station,'variable':variable,'count':len(arr),'latest_utc':last,'age_hours':round(age,2) if age is not None else None,'fresh_72h':age is not None and -2<=age<=72,'status':'FRESH' if age is not None and -2<=age<=72 else 'STALE' if arr else 'NOT_RETRIEVED'})
 if not any(x['node']==node and x['fresh_72h'] for x in rows):missing.append(node)

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

# Reach mass balance: only explicitly configured, verified, contemporaneous discharge series.
config=load('config/mass_balance_reaches.json') or {'reaches':[]};balances=[]
def discharge(spec):
 obj=normalized.get(spec.get('node'),{});src=spec.get('source')
 if src=='usgs':return obj.get('usgs',{}).get(str(spec.get('site')),{}).get('00060',[])
 if src=='usace':return obj.get('usace',{}).get('discharge',[])
 return []
def nearest(arr,target,minutes=60):
 if not arr:return None
 x=min(arr,key=lambda x:abs((timeparse(x['time'])-target).total_seconds()))
 return x if abs((timeparse(x['time'])-target).total_seconds())<=minutes*60 else None
for r in config['reaches']:
 if not r.get('enabled'):continue
 if r.get('lag_hours') is None or not r.get('lag_source') or r.get('storage_change_cfs') is None or r.get('uncertainty_pct') is None:
  balances.append({'reach':r['name'],'status':'BLOCKED_MISSING_LAG_STORAGE_OR_UNCERTAINTY'});continue
 down=discharge(r['downstream']);up=discharge(r['upstream']);samples=[]
 for d in down:
  td=timeparse(d['time']);tu=td-dt.timedelta(hours=float(r['lag_hours']));u=nearest(up,tu)
  tributaries=[nearest(discharge(s),tu) for s in r.get('tributaries',[])];diversions=[nearest(discharge(s),tu) for s in r.get('diversions',[])]
  if not u or any(x is None for x in tributaries+diversions):continue
  if any(str(x.get('unit','')).lower() not in ('ft3/s','cfs','ft^3/s') for x in [d,u]+tributaries+diversions):continue
  expected=u['value']+sum(x['value'] for x in tributaries)-sum(x['value'] for x in diversions)-float(r['storage_change_cfs'])
  residual=d['value']-expected;tol=max(1,abs(expected))*float(r['uncertainty_pct'])/100
  samples.append({'time_utc':d['time'],'observed_downstream_cfs':d['value'],'expected_cfs':round(expected,2),'residual_cfs':round(residual,2),'within_assumed_uncertainty':abs(residual)<=tol})
 balances.append({'reach':r['name'],'status':'EVALUATED' if samples else 'INSUFFICIENT_TIME_ALIGNED_Q','samples':samples,'assumptions':{'lag_hours':r['lag_hours'],'lag_source':r['lag_source'],'storage_change_cfs':r['storage_change_cfs'],'uncertainty_pct':r['uncertainty_pct']}})

out={'generated_utc':NOW.isoformat(),'nodes':normalized,'coverage':rows,'stage_crosschecks':cross,'mass_balance':balances,'notes':['No NOAA stage-to-discharge conversion inferred.','NOAA primary assumed native stage only; NOAA secondary discharge retained in raw stageflow until field/units validation.','USGS OGC routes retained raw; legacy IV used for normalized values until OGC schema is verified against actual GitHub results.','Empty CWMS approved-series config means no operational series acquired.','No mass balance computed without documented lag, storage and complete time-aligned discharge.']}
(ROOT/'normalized_network.json').write_text(json.dumps(out,separators=(',',':')))
with (ROOT/'station_coverage.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(ROOT/'qc_report.json').write_text(json.dumps({'generated_utc':NOW.isoformat(),'node_count':len(normalized),'expected_node_count':42,'nodes_without_fresh_observation':missing,'stage_crosschecks':cross,'mass_balance':balances,'coverage_counts':{'fresh':sum(r['fresh_72h'] for r in rows),'total':len(rows)},'caveats':out['notes']},indent=2))
print('Normalized',len(normalized),'nodes; fresh source/variable rows',sum(r['fresh_72h'] for r in rows),'/',len(rows),'nodes without fresh observation',len(missing))
if len(normalized)!=42:raise SystemExit('Network coverage registry mismatch')
