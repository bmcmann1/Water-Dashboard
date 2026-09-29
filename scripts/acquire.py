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

def hefs_acquire(stations):
    """Use paths verified in the archived NOAA HEFS OpenAPI YAML (2026-09-29)."""
    base='https://api.water.noaa.gov/hefs/v1'
    # Keep the authoritative schema alongside the resulting data. YAML is not JSON.
    _, schema=get('HEFS YAML specification',base+'/schema/','raw/hefs/openapi.yaml')
    catalog={'schema_url':base+'/schema/','documented_paths':['/hefs/v1/locations/','/hefs/v1/hydrograph-quantiles/','/hefs/v1/headers/','/hefs/v1/ensembles/'],'schema_http_status':schema['http_status'],'schema_bytes':schema['bytes']}
    save('hefs_endpoint_catalog.json',json.dumps(catalog,indent=2).encode())
    for station in stations:
        lid=station.get('lid')
        if not lid:continue
        h={'status':'LOCATION_QUERY_PENDING','attempts':[],'available_parameters':[]}
        station['hefs']=h
        url=base+'/locations/?'+urllib.parse.urlencode({'location_id':lid})
        parsed,e=get('HEFS '+lid+' locations',url,'raw/hefs/'+lid+'/locations.json',timeout=30)
        h['attempts'].append({'url':url,'http_status':e['http_status'],'json_ok':e['json_ok'],'bytes':e['bytes'],'error':e['error']})
        # Location responses may be an array or wrapped in a locations/data object.
        if isinstance(parsed,list): locations=parsed
        elif isinstance(parsed,dict):
            locations=parsed.get('locations',parsed.get('data',[]))
            if isinstance(locations,dict):locations=[locations]
            if not locations and parsed.get('location_id'):locations=[parsed]
        else:locations=[]
        if not isinstance(locations,list):locations=[]
        parameter_ids=set()
        for loc in locations:
            if not isinstance(loc,dict) or str(loc.get('location_id','')).upper()!=lid.upper():continue
            for p in loc.get('parameters',[]) or []:
                if isinstance(p,dict):
                    pid=p.get('parameter_id')
                    if pid:parameter_ids.add(str(pid))
                elif isinstance(p,str):parameter_ids.add(p)
        h['available_parameters']=sorted(parameter_ids)
        if not e['json_ok']:
            h['status']='HEFS_LOCATION_REQUEST_FAILED';continue
        if not parameter_ids:
            h['status']='NO_CACHED_HEFS_PARAMETERS_FOR_GAUGE';continue
        for pid in sorted(parameter_ids):
            url=base+'/hydrograph-quantiles/?'+urllib.parse.urlencode({'location_id':lid,'parameter_id':pid})
            parsed,q=get('HEFS '+lid+' hydrograph quantiles '+pid,url,'raw/hefs/'+lid+'/quantiles_'+re.sub('[^a-zA-Z0-9_-]','_',pid)+'.json',timeout=40)
            h['attempts'].append({'url':url,'parameter_id':pid,'http_status':q['http_status'],'json_ok':q['json_ok'],'bytes':q['bytes'],'error':q['error'],'candidate_timestamps':find_dates(parsed) if parsed is not None else []})
            time.sleep(.2)
        h['status']='HEFS_QUANTILE_JSON_RETRIEVED_QC_PENDING' if any(x.get('parameter_id') and x['json_ok'] for x in h['attempts']) else 'HEFS_QUANTILE_RETRIEVAL_FAILED'
    return catalog

def main():
    nodes=[dict(x) for x in REG['reaches']+REG['junctions']]
    # Explicitly flag that CIRI2 is an Ohio stage gauge, not a Mississippi-below-Ohio discharge gauge.
    for n in nodes:
        if n.get('lid')=='CIRI2':n['network_warning']='Ohio River stage at Cairo; not Mississippi downstream-of-confluence discharge'
    results=[]
    for n in nodes:
        print('NWPS',n['name'],n.get('lid'),flush=True);results.append(nwps(n))
    catalog=hefs_acquire(results)
    spec_url=catalog['schema_url'] if catalog['schema_http_status']==200 else None
    audit={'started_utc':LOG[0]['retrieved_utc'] if LOG else UTC(),'completed_utc':UTC(),'network_nodes':len(results),'nwps_lids':sum(bool(r.get('lid')) for r in results),'hefs_schema_url':spec_url,'stations':results,'requests':LOG,'certification':'RAW_ACQUISITION_ONLY_NOT_HYDRAULIC_QC'}
    save('audit.json',json.dumps(audit,indent=2).encode())
    success=sum(x['json_ok'] for x in LOG if x['label'].startswith('NWPS'))
    hefs_ok=sum(x['json_ok'] for x in LOG if 'hydrograph quantiles' in x['label'])
    summary=f'# Mississippi NOAA + HEFS acquisition\n\nRun completed {UTC()}\n\n- Network locations: {len(results)}\n- NOAA IDs in existing registry: {audit["nwps_lids"]}\n- Successful NWPS JSON responses: {success}\n- HEFS YAML specification downloaded: {catalog["schema_http_status"]==200}\n- Successful HEFS quantile JSON responses: {hefs_ok}\n- Status: **raw acquisition only; hydraulic QC and datum certification pending**\n\nSee audit.json, hefs_endpoint_catalog.json and raw/ in the downloadable artifact.\n'
    save('SUMMARY.md',summary.encode());print(summary)
if __name__=='__main__':main()
