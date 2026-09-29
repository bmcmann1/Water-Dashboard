#!/usr/bin/env python3
"""Read-only, bounded USGS/USACE acquisition. Never infer discharge from stage."""
import csv,datetime as dt,hashlib,json,pathlib,re,time,urllib.parse,urllib.request,urllib.error
ROOT=pathlib.Path('output');ROOT.mkdir(exist_ok=True)
REG=json.loads(pathlib.Path('network_registry.json').read_text())
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
 'grafton':['05587450']}
# Known alternatives and operational station aliases: discovery only, not assumed live data.
CWMS_TERMS={'oldriver':['Old River','ORCC','Atchafalaya'],'morganza':['Morganza'],
 'bonnet':['Bonnet Carre'],'rrl':['Red River Landing','Tarbert'],
 'westpointe':['West Pointe'],'natchez':['Natchez'],'vicksburg':['Vicksburg'],
 'arkcity':['Arkansas City'],'greenville':['Greenville'],'white':['St Charles'],
 'stfrancis':['Madison'],'hatchie':['Rialto'],'meramec':['Valley Park','Fenton'],
 'kaskaskia':['Fayetteville'],'lafourche':['Bayou Lafourche']}
def fetch(label,url,rel,accept='application/json'):
 p=ROOT/rel;p.parent.mkdir(parents=True,exist_ok=True)
 entry={'label':label,'url':url,'file':str(rel),'retrieved_utc':UTC().isoformat(),'http_status':None,'bytes':0,'sha256':None,'json_ok':False,'error':None}
 try:
  req=urllib.request.Request(url,headers={**HEAD,'Accept':accept})
  with urllib.request.urlopen(req,timeout=28) as r:
   entry['http_status']=r.status;entry['content_type']=r.headers.get('Content-Type');data=r.read(LIMIT+1)
  if len(data)>LIMIT:raise ValueError('response exceeds 12 MB per-request cap')
  p.write_bytes(data);entry['bytes']=len(data);entry['sha256']=hashlib.sha256(data).hexdigest()
  try: parsed=json.loads(data);entry['json_ok']=True
  except (ValueError,UnicodeError):parsed=None
  return parsed,entry
 except urllib.error.HTTPError as e:entry['http_status']=e.code;entry['error']=str(e)
 except Exception as e:entry['error']=repr(e)
 finally:LOG.append(entry)
 return None,entry

def usgs(sid):
 out={'site':sid,'routes':[],'parameters':{}}
 # Three routes: new continuous API, new latest API, legacy IV fallback. 00060 Q, 00065 stage, 63160 NAVD88 WSE.
 for code in ['00060','00065','63160']:
  for route,base,query in [
   ('continuous','https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items',{'f':'json','monitoring_location_id':'USGS-'+sid,'parameter_code':code,'time':'P3D','limit':1500,'skipGeometry':'true'}),
   ('latest','https://api.waterdata.usgs.gov/ogcapi/v1/collections/latest-continuous/items',{'f':'json','monitoring_location_id':'USGS-'+sid,'parameter_code':code,'limit':5,'skipGeometry':'true'}),
   ('legacy','https://waterservices.usgs.gov/nwis/iv/',{'format':'json','sites':sid,'parameterCd':code,'period':'P3D','siteStatus':'all'})]:
   url=base+'?'+urllib.parse.urlencode(query)
   data,e=fetch('USGS '+sid+' '+code+' '+route,url,'raw/usgs/'+sid+'/'+code+'_'+route+'.json')
   count=len(data.get('features',[])) if isinstance(data,dict) and isinstance(data.get('features'),list) else None
   if route=='legacy' and isinstance(data,dict):count=sum(len(v.get('values',[{}])[0].get('value',[])) for v in data.get('value',{}).get('timeSeries',[]) if v.get('values'))
   out['routes'].append({'parameter':code,'route':route,'status':e['http_status'],'json_ok':e['json_ok'],'records':count,'error':e['error']})
   time.sleep(.09)
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
 # The registry may include historical IDs; absence of records must remain visible.
 summaries={sid:usgs(sid) for sid in sorted(site_nodes)}
 discovery=cwms_discovery()
 summary={'generated_utc':UTC().isoformat(),'scope':'42 nodes; 3 USGS routes per site/parameter; bounded USACE catalog discovery','site_to_nodes':site_nodes,'usgs':summaries,'cwms_discovery':discovery,'request_count':len(LOG),'successful_json':sum(x['json_ok'] for x in LOG),'failed_requests':sum(not x['json_ok'] for x in LOG),'important_limits':['CWMS catalog discovery does not establish that time series are active; review catalog identifiers and select validated flow/operations series for next run.','USGS latest route is not a three-day history; continuous and legacy are history routes.','No Q imputation, no inferred NAVD88 conversions, no unverified mass balance.']}
 (ROOT/'acquisition_summary.json').write_text(json.dumps(summary,indent=2))
 (ROOT/'request_audit.json').write_text(json.dumps(LOG,indent=2))
 print(json.dumps({'sites':len(site_nodes),'requests':len(LOG),'successful_json':summary['successful_json'],'failed':summary['failed_requests']},indent=2))
 if summary['successful_json']==0:raise SystemExit('All acquisition routes failed; no empty dashboard generated')
if __name__=='__main__':main()
