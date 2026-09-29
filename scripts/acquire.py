#!/usr/bin/env python3
"""Standard-library, read-only NOAA network acquisition. No guessed HEFS paths."""
import datetime as dt, hashlib, json, os, pathlib, re, time, urllib.error, urllib.parse, urllib.request
ROOT=pathlib.Path('output'); ROOT.mkdir(exist_ok=True)
REG=json.load(open('network_registry.json',encoding='utf-8'))
UTC=lambda:dt.datetime.now(dt.timezone.utc).isoformat()
LOG=[]; MAX_BYTES=25_000_000
HEAD={'User-Agent':'Mississippi-Hydraulic-Network-Research/1.0 (GitHub Actions)','Accept':'application/json, application/yaml, */*'}
def save(name,data):
    p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
def get(label,url,filename,timeout=25):
    entry={'label':label,'url':url,'retrieved_utc':UTC(),'http_status':None,'bytes':0,'sha256':None,'json_ok':False,'error':None,'file':filename}
    try:
        req=urllib.request.Request(url,headers=HEAD)
        with urllib.request.urlopen(req,timeout=timeout) as resp:
            entry['http_status']=resp.status;entry['content_type']=resp.headers.get('Content-Type');data=resp.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:raise ValueError('response exceeds 25MB safety limit')
        entry['bytes']=len(data);entry['sha256']=hashlib.sha256(data).hexdigest();save(filename,data)
        try: parsed=json.loads(data);entry['json_ok']=True
        except (ValueError,UnicodeError): parsed=None
        entry['top_keys']=list(parsed)[:35] if isinstance(parsed,dict) else None
        return parsed,entry
    except urllib.error.HTTPError as e:entry['http_status']=e.code;entry['error']=str(e)
    except Exception as e:entry['error']=repr(e)
    finally:LOG.append(entry)
    return None,entry

def find_dates(obj,limit=8):
    found=[]
    def visit(x,path='',depth=0):
        if len(found)>=limit or depth>5:return
        if isinstance(x,dict):
            for k,v in x.items():
                p=path+'.'+k if path else k
                if isinstance(v,str) and ('time' in k.lower() or 'date' in k.lower()) and re.search(r'20\d\d-',v):found.append({'field':p,'value':v})
                elif isinstance(v,(dict,list)):visit(v,p,depth+1)
        elif isinstance(x,list):
            for v in x[:3]:visit(v,path+'[]',depth+1)
    visit(obj);return found

def nwps(station):
    lid=station.get('lid'); sid=station.get('id','unknown'); result={'id':sid,'name':station['name'],'lid':lid,'usgs_candidate':station.get('usgs'),'kind':station.get('kind'),'nwps':{},'hefs':{'status':'not_tested'}}
    if not lid:result['nwps_status']='NO_VERIFIED_NOAA_LID';return result
    base='https://api.water.noaa.gov/nwps/v1/gauges/'+urllib.parse.quote(lid)
    for key,suffix in [('metadata',''),('stageflow','/stageflow'),('ratings','/ratings')]:
        parsed,entry=get('NWPS '+lid+' '+key,base+suffix,'raw/nwps/'+lid+'/'+key+'.json')
        result['nwps'][key]={'http_status':entry['http_status'],'json_ok':entry['json_ok'],'error':entry['error'],'candidate_timestamps':find_dates(parsed) if parsed else []}
        if key=='metadata' and isinstance(parsed,dict):
            result['nwps'][key].update({'returned_lid':parsed.get('lid'),'rfc':parsed.get('rfc'),'images':parsed.get('images'),'datums':parsed.get('datums'),'reachId':parsed.get('reachId'),'usgsId':parsed.get('usgsId')})
        if key=='stageflow' and isinstance(parsed,dict):
            for section in ('observed','forecast'):
                v=parsed.get(section); result['nwps'][key][section]={'present':isinstance(v,dict),'keys':list(v) if isinstance(v,dict) else None,'issuedTime':v.get('issuedTime') if isinstance(v,dict) else None,'data_count':len(v.get('data',[])) if isinstance(v,dict) and isinstance(v.get('data'),list) else None}
        if key=='ratings' and isinstance(parsed,dict):result['nwps'][key]['rating_points']=len(parsed.get('data',[])) if isinstance(parsed.get('data'),list) else None
        time.sleep(.12)
    return result

def discover_hefs():
    # NOAA publishes Swagger UI, but its OpenAPI schema filename may vary. Probe docs first, then spec candidates.
    base='https://api.water.noaa.gov/hefs/v1'
    specs=[base+'/schema/',base+'/openapi.json',base+'/swagger.json',base+'/v3/api-docs',base+'/api-docs',base+'/openapi.yaml']
    for url in specs:
        parsed,entry=get('HEFS schema discovery',url,'raw/hefs/schema_'+str(specs.index(url))+'.response')
        if isinstance(parsed,dict) and ('paths' in parsed or 'openapi' in parsed or 'swagger' in parsed):return parsed,url
    for page in [base+'/swagger-ui/',base+'/redoc/']:
        parsed,entry=get('HEFS documentation page',page,'raw/hefs/'+('swagger-ui.html' if 'swagger' in page else 'redoc.html'))
        # HTML is archived for diagnosing the actual schema URL; never guess data endpoints.
    return None,None

def hefs_paths(spec):
    paths=spec.get('paths',{}); rows=[]
    for path,methods in paths.items():
        if not isinstance(methods,dict):continue
        method=methods.get('get');
        if not isinstance(method,dict):continue
        params=(spec.get('parameters',{}) if isinstance(spec.get('parameters'),dict) else {})
        raw=methods.get('parameters',[])+method.get('parameters',[])
        details=[]
        for p in raw:
            if '$ref' in p:
                p=params.get(p['$ref'].rsplit('/',1)[-1],{})
            details.append({'name':p.get('name'),'in':p.get('in'),'required':p.get('required',False),'type':p.get('type') or p.get('schema',{}).get('type'),'description':p.get('description','')[:180]})
        rows.append({'path':path,'summary':method.get('summary'),'parameters':details})
    return rows

def hefs_acquire(spec,rows,stations):
    # Query only schema-confirmed, station-addressable GET paths whose required parameters can be supplied.
    candidates=[]
    for r in rows:
        p=r['path'];params=r['parameters'];names={x['name'].lower() for x in params if x.get('name')}
        loc=[x for x in params if x.get('name') and any(t in x['name'].lower() for t in ('location','station','identifier','lid'))]
        if not loc or not any(t in (p+' '+str(r['summary'])).lower() for t in ('quantile','ensemble','forecast','location')):continue
        if any(x['required'] and x['name'] not in [y['name'] for y in loc] for x in params):continue
        candidates.append(r)
    for station in stations:
        lid=station.get('lid');
        if not lid:continue
        station['hefs']={'status':'NO_SCHEMA_COMPATIBLE_PATH' if not candidates else 'attempted','attempts':[]}
        for r in candidates[:4]:
            path=r['path'];query={};skip=False
            for x in r['parameters']:
                name=x['name'];
                if not name:continue
                if any(t in name.lower() for t in ('location','station','identifier','lid')):
                    if '{'+name+'}' in path:path=path.replace('{'+name+'}',urllib.parse.quote(lid))
                    else:query[name]=lid
            if '{' in path:continue
            # Absolute servers in OAS3 are supported; otherwise NOAA's HEFS base.
            server=spec.get('servers',[{'url':'https://api.water.noaa.gov/hefs/v1'}])[0]['url'] if spec.get('servers') else 'https://api.water.noaa.gov/hefs/v1'
            if not server.startswith('https://api.water.noaa.gov'):server='https://api.water.noaa.gov/hefs/v1'
            url=server.rstrip('/')+'/'+path.lstrip('/')
            if query:url+='?'+urllib.parse.urlencode(query)
            safe=re.sub('[^a-zA-Z0-9_-]+','_',r['path']).strip('_')[:75]
            parsed,entry=get('HEFS '+lid+' '+r['path'],url,'raw/hefs/'+lid+'/'+safe+'.json',timeout=35)
            station['hefs']['attempts'].append({'path':r['path'],'http_status':entry['http_status'],'json_ok':entry['json_ok'],'bytes':entry['bytes'],'error':entry['error'],'candidate_timestamps':find_dates(parsed) if parsed else []})
            time.sleep(.2)
        if any(x['json_ok'] for x in station['hefs']['attempts']):station['hefs']['status']='HEFS_JSON_RETRIEVED_SCHEMA_QC_PENDING'
        elif station['hefs']['attempts']:station['hefs']['status']='HEFS_NO_SUCCESSFUL_RESPONSE'

def main():
    nodes=[dict(x) for x in REG['reaches']+REG['junctions']]
    # Explicitly flag that CIRI2 is an Ohio stage gauge, not a Mississippi-below-Ohio discharge gauge.
    for n in nodes:
        if n.get('lid')=='CIRI2':n['network_warning']='Ohio River stage at Cairo; not Mississippi downstream-of-confluence discharge'
    results=[]
    for n in nodes:
        print('NWPS',n['name'],n.get('lid'),flush=True);results.append(nwps(n))
    spec,spec_url=discover_hefs();rows=hefs_paths(spec) if spec else []
    save('hefs_endpoint_catalog.json',json.dumps({'schema_url':spec_url,'paths':rows},indent=2).encode())
    if spec:hefs_acquire(spec,rows,results)
    else:
        for r in results:
            if r.get('lid'):r['hefs']={'status':'HEFS_SCHEMA_NOT_DISCOVERED','note':'Documentation HTML archived; manually inspect its configured OpenAPI URL.'}
    audit={'started_utc':LOG[0]['retrieved_utc'] if LOG else UTC(),'completed_utc':UTC(),'network_nodes':len(results),'nwps_lids':sum(bool(r.get('lid')) for r in results),'hefs_schema_url':spec_url,'stations':results,'requests':LOG,'certification':'RAW_ACQUISITION_ONLY_NOT_HYDRAULIC_QC'}
    save('audit.json',json.dumps(audit,indent=2).encode())
    success=sum(x['json_ok'] for x in LOG if x['label'].startswith('NWPS'))
    hefs_ok=sum(x['json_ok'] for x in LOG if x['label'].startswith('HEFS ') and 'schema' not in x['label'])
    summary=f'# Mississippi NOAA + HEFS acquisition\n\nRun completed {UTC()}\n\n- Network locations: {len(results)}\n- NOAA IDs in existing registry: {audit["nwps_lids"]}\n- Successful NWPS JSON responses: {success}\n- HEFS OpenAPI schema discovered: {bool(spec)}\n- Successful HEFS location JSON responses: {hefs_ok}\n- Status: **raw acquisition only; hydraulic QC and datum certification pending**\n\nSee audit.json, hefs_endpoint_catalog.json and raw/ in the downloadable artifact.\n'
    save('SUMMARY.md',summary.encode());print(summary)
if __name__=='__main__':main()
