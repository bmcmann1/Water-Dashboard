#!/usr/bin/env python3
"""Read-only, bounded USGS/USACE acquisition. Never infer discharge from stage."""
import csv,datetime as dt,hashlib,json,pathlib,re,time,os,urllib.parse,urllib.request,urllib.error
ROOT=pathlib.Path('output');ROOT.mkdir(exist_ok=True)
REG=json.loads(pathlib.Path('network_registry.json').read_text())
PRIORITY=json.loads(pathlib.Path('config/priority_tributary_policy.json').read_text())['rivers']
CANDIDATES=json.loads(pathlib.Path('config/tributary_candidates.json').read_text())['nodes']
UTC=lambda:dt.datetime.now(dt.timezone.utc)
LOG=[];LIMIT=12_000_000
HEAD={'User-Agent':'Mississippi-Hydraulic-Network/2.0 (GitHub Actions; research)','Accept':'application/json'}
# Reference stations, not confluence gauges. Candidates must be confirmed by telemetry and geography.
REFERENCES={
 'illinois':['05587060'],'missouri':['06935965'],'meramec':['07019130'],
 'kaskaskia':['05595000'],'bigmuddy':['05599500'],'hatchie':['07029500'],
 'loosahatchie':['07030357','07030240'],'wolf':['07031740','07031650'],
 'stfrancis':[],'white':['07077830'],'arkansas':['07265280'],
 'yazoo':['07288800'],'bigblack':['07290000'],'homochitto':['07292500'],
 'bayousara':['07373300'],'lafourche':['07380401'],
 'davis':['295501090190400'],'caernarvon':['295124089542100'],
 'bellechasse':['07374525'],'baton':['07374000'],'natchez':['07290880'],
 'vicksburg':['07289000'],'thebes':['07022000'],'stlouis':['07010000'],
 'grafton':['05587450'], 'cuivre':['05514500'], 'obion':['07026040'], 'salt':[], 'forkeddeer':[]}
# Known alternatives and operational station aliases: discovery only, not assumed live data.
CWMS_TERMS={'oldriver':['Old River','ORCC','Atchafalaya'],'morganza':['Morganza'],
 'bonnet':['Bonnet Carre'],'rrl':['Red River Landing','Tarbert'],
 'westpointe':['West Pointe'],'natchez':['Natchez'],'vicksburg':['Vicksburg'],
 'arkcity':['Arkansas City'],'greenville':['Greenville'],'white':['St Charles'],
 'stfrancis':['Madison'],'hatchie':['Rialto'],'meramec':['Valley Park','Fenton'],
 'kaskaskia':['Fayetteville'],'lafourche':['Bayou Lafourche']}
def fetch(label,url,rel,accept='application/json'):
 p=ROOT/rel;p.parent.mkdir(parents=True,exist_ok=True)
 entry={'label':label,'url':url,'file':str(rel),'retrieved_utc':UTC().isoformat(),'http_status':None,'bytes':0,'sha256':None,'json_ok':False,'error':None,'attempts':0,'retry_wait_seconds':[]}
 for attempt in range(1,5):
  entry['attempts']=attempt
  try:
   req=urllib.request.Request(url,headers={**HEAD,'Accept':accept})
   with urllib.request.urlopen(req,timeout=35) as r:
    entry['http_status']=r.status;entry['content_type']=r.headers.get('Content-Type');data=r.read(LIMIT+1)
   if len(data)>LIMIT:raise ValueError('response exceeds 12 MB per-request cap')
   parsed=json.loads(data)
   p.write_bytes(data);entry['bytes']=len(data);entry['sha256']=hashlib.sha256(data).hexdigest();entry['json_ok']=True;entry['error']=None
   LOG.append(entry);return parsed,entry
  except urllib.error.HTTPError as e:
   entry['http_status']=e.code;entry['error']=str(e)
   if e.code not in (429,500,502,503,504) or attempt==4:break
   try:retry_after=min(90,max(0,float(e.headers.get('Retry-After','0'))))
   except (TypeError,ValueError):retry_after=0
   wait=max(retry_after,min(45,2**attempt+(.3*attempt)))
  except (urllib.error.URLError,TimeoutError) as e:
   entry['error']=repr(e)
   if attempt==4:break
   wait=min(45,2**attempt+(.3*attempt))
  except Exception as e:
   entry['error']=repr(e);break
  entry['retry_wait_seconds'].append(wait);time.sleep(wait)
 LOG.append(entry);return None,entry

def usgs(sid):
 """Attempt three independently addressable USGS retrieval routes per parameter.

 IV is the canonical instantaneous record. Daily values are independent published
 aggregates and MUST NOT be substituted for instantaneous flow. OGC responses are
 archived for schema review; they are not silently normalized as legacy IV.
 """
 out={'site':sid,'routes':[],'parameters':{}}
 for code in ('00060','00065','63160'):
  routes=[
   ('legacy_iv','https://waterservices.usgs.gov/nwis/iv/',{'format':'json','sites':sid,'parameterCd':code,'period':'P2D','siteStatus':'all'}),
   ('ogc_continuous','https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items',{'monitoring_location_id':'USGS-'+sid,'parameter_code':code,'limit':96}),
   ('legacy_dv','https://waterservices.usgs.gov/nwis/dv/',{'format':'json','sites':sid,'parameterCd':code,'period':'P3D','siteStatus':'all'})]
  for route,base,query in routes:
   data,e=fetch('USGS '+sid+' '+code+' '+route,base+'?'+urllib.parse.urlencode(query),
                'raw/usgs/'+sid+'/'+code+'_'+route+'.json')
   count=(sum(len(block.get('value',[])) for ts in data.get('value',{}).get('timeSeries',[])
           for block in ts.get('values',[])) if isinstance(data,dict) and route!='ogc_continuous'
          else len(data.get('features',[])) if isinstance(data,dict) and route=='ogc_continuous' else 0)
   out['routes'].append({'parameter':code,'route':route,'url':e['url'],'status':e['http_status'],
     'json_ok':e['json_ok'],'records':count,'error':e['error'],
     'retrieved_utc':e['retrieved_utc'],'bytes':e['bytes'],'sha256':e['sha256'],
     'use_for_instantaneous':route=='legacy_iv' and count>0})
   # The existing normalizer consumes the legacy filename. Avoid an extra file copy.
   if route=='legacy_iv' and e['json_ok']:
    original=ROOT/'raw/usgs'/sid/(code+'_legacy_iv.json')
    original.rename(ROOT/'raw/usgs'/sid/(code+'_legacy.json'))
    e['file']='raw/usgs/'+sid+'/'+code+'_legacy.json'
 return out

def cwms_discovery():
 # API supports filtered catalog; never pull national catalogs without a limit.
 base='https://cwms-data.usace.army.mil/cwms-data'
 schema,_=fetch('CWMS OpenAPI','https://cwms-data.usace.army.mil/cwms-data/swagger.json','raw/usace/swagger.json')
 results=[]
 for node,terms in CWMS_TERMS.items():
  for term in terms:
   for route,endpoint,query in [
    ('timeseries_catalog',base+'/catalog/timeseries',{'like':'*'+term.replace(' ','*')+'*','page-size':100}),
    ('locations_catalog',base+'/catalog/locations',{'like':'*'+term.replace(' ','*')+'*','page-size':100})]:
    url=endpoint+'?'+urllib.parse.urlencode(query)
    safe=re.sub('[^a-z0-9]+','_',term.lower())
    data,e=fetch('CWMS '+node+' '+term+' '+route,url,'raw/usace/discovery/'+node+'_'+safe+'_'+route+'.json')
    results.append({'node':node,'term':term,'route':route,'http_status':e['http_status'],'json_ok':e['json_ok'],'error':e['error'],'file':e['file'] if e['json_ok'] else None})
    time.sleep(.1)
 return results

def main():
 nodes=REG['reaches']+REG['junctions'];site_nodes={}
 for n in nodes:
  sid=n.get('usgs');
  if sid:site_nodes.setdefault(str(sid),[]).append(n['id'])
  for sid in REFERENCES.get(n['id'],[]):site_nodes.setdefault(sid,[]).append(n['id'])
  for sid in PRIORITY.get(n['id'],{}).get('usgs_flow',[])+PRIORITY.get(n['id'],{}).get('usgs_stage',[]):site_nodes.setdefault(str(sid),[]).append(n['id'])
  for sid in CANDIDATES.get(n['id'],{}).get('usgs_sites',[]):site_nodes.setdefault(sid,[]).append(n['id'])
 # The registry may include historical IDs; absence of records must remain visible.
 summaries={sid:usgs(sid) for sid in sorted(site_nodes)}
 discovery=cwms_discovery() if os.getenv("REFRESH_USACE_CATALOG", "0")=="1" else []
 summary={'generated_utc':UTC().isoformat(),'scope':str(len(nodes))+' nodes; three logged USGS routes per site-variable; optional CWMS catalog refresh','site_to_nodes':site_nodes,'usgs':summaries,'cwms_discovery':discovery,'request_count':len(LOG),'successful_json':sum(x['json_ok'] for x in LOG),'failed_requests':sum(not x['json_ok'] for x in LOG),'upstream_candidate_review':CANDIDATES,'important_limits':['CWMS catalog discovery does not establish that time series are active; review catalog identifiers and select validated flow/operations series for next run.','Only legacy instantaneous values are normalized; OGC and daily-value responses are independently logged verification/discovery evidence, not interchangeable instantaneous observations.','No Q imputation, no inferred NAVD88 conversions, no unverified mass balance.']}
 (ROOT/'acquisition_summary.json').write_text(json.dumps(summary,indent=2))
 (ROOT/'request_audit.json').write_text(json.dumps(LOG,indent=2))
 print(json.dumps({'sites':len(site_nodes),'requests':len(LOG),'successful_json':summary['successful_json'],'failed':summary['failed_requests']},indent=2))
 if summary['successful_json']==0:raise SystemExit('All acquisition routes failed; no empty dashboard generated')
if __name__=='__main__':main()
