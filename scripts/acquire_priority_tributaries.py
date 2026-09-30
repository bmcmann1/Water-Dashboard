#!/usr/bin/env python3
"""Acquire supplemental major-tributary evidence with auditable, bounded requests.

For each configured NOAA checkpoint this archives metadata, stage/forecast, ratings,
and—when metadata exposes a reachId—the NWM analysis-assimilation streamflow for the
same location.  Stage is never converted to flow.
"""
import datetime as dt,hashlib,json,pathlib,urllib.request,urllib.error,urllib.parse,time,re
ROOT=pathlib.Path('output');ROOT.mkdir(exist_ok=True)
CFG=json.loads(pathlib.Path('config/priority_tributary_policy.json').read_text())
LOG=[];CACHE={}
HEAD={'User-Agent':'MississippiHydraulicNetwork/16','Accept':'application/json, text/html, */*'}
def fetch(node,station,variable,route,url,binary=False):
    key=(station,variable,route)
    if key in CACHE:
        row=dict(CACHE[key]);row.update(node=node,reused=True);LOG.append(row);return None
    row={'node':node,'station':station,'variable':variable,'route':route,'url':url,'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'http_status':None,'bytes':0,'records':0,'error':None,'reused':False}
    obj=None
    try:
        req=urllib.request.Request(url,headers=HEAD)
        with urllib.request.urlopen(req,timeout=22) as r:
            row['http_status']=r.status;raw=r.read(4_000_001)
        if len(raw)>4_000_000:raise ValueError('Response over 4 MB')
        row['bytes']=len(raw);row['sha256']=hashlib.sha256(raw).hexdigest()
        if not binary:
            obj=json.loads(raw)
            if route=='nwps_stageflow':row['records']=len((obj.get('observed') or {}).get('data') or []) if isinstance(obj,dict) else 0
            elif route in ('nwps_metadata','nwps_ratings'):row['records']=int(isinstance(obj,dict))
            elif route.startswith('nwm_'):
                def count(x,depth=0):
                    if depth>6:return 0
                    if isinstance(x,dict):return (len(x.get('data',[])) if isinstance(x.get('data'),list) else 0)+sum(count(v,depth+1) for v in x.values() if isinstance(v,(dict,list)))
                    if isinstance(x,list):return sum(count(v,depth+1) for v in x[:15])
                    return 0
                row['records']=count(obj)
        target=ROOT/'raw/priority'/station;target.mkdir(parents=True,exist_ok=True)
        suffix='.html' if binary else '.json'
        (target/(variable+'_'+route+suffix)).write_bytes(raw)
    except urllib.error.HTTPError as e:row['http_status']=e.code;row['error']=str(e)
    except Exception as e:row['error']=repr(e)
    CACHE[key]=dict(row);LOG.append(row);return obj

lids={}
for node,cfg in CFG['rivers'].items():
    for lid in cfg.get('noaa_stage',[]):lids.setdefault(lid,set()).add(node)
# Reconciliation checkpoint gauges not all belong to registry nodes.
for lid,node in [('HRCM7','meramec'),('EADM7','meramec')]:lids.setdefault(lid,set()).add(node)
for lid,nodes in lids.items():
    base='https://api.water.noaa.gov/nwps/v1/gauges/'+lid
    meta=fetch(sorted(nodes)[0],lid,'metadata','nwps_metadata',base)
    for node in sorted(nodes)[1:]:
        row=dict(CACHE[(lid,'metadata','nwps_metadata')]);row.update(node=node,reused=True);LOG.append(row)
    fetch(sorted(nodes)[0],lid,'stage','nwps_stageflow',base+'/stageflow')
    fetch(sorted(nodes)[0],lid,'ratings','nwps_ratings',base+'/ratings')
    reach=(meta or {}).get('reachId') if isinstance(meta,dict) else None
    if reach:
        nurl='https://api.water.noaa.gov/nwps/v1/reaches/'+urllib.parse.quote(str(reach),safe='')+'/streamflow?series=analysis_assimilation'
        fetch(sorted(nodes)[0],lid,'nwm','nwm_analysis_assimilation',nurl)
    time.sleep(.08)

# White River quantitative anchor at Clarendon: dedicated USACE SWL table.
url='https://www.swl-wc.usace.army.mil/pages/data/tabular/htm/clarendo.htm'
try:
    req=urllib.request.Request(url,headers=HEAD)
    with urllib.request.urlopen(req,timeout=22) as r:raw=r.read(2_000_001);status=r.status
    if len(raw)>2_000_000:raise ValueError('Clarendon response over 2 MB')
    (ROOT/'raw/priority').mkdir(parents=True,exist_ok=True);(ROOT/'raw/priority/clarendon.html').write_bytes(raw)
    text=re.sub(r'<[^>]+>',' ',raw.decode('utf-8','replace'));text=re.sub(r'\s+',' ',text)
    # Date, local clock, stage, flow.  SWL labels the clock CST/CDT; use America/Chicago.
    from zoneinfo import ZoneInfo
    rows=[]
    pat=re.compile(r'(\d{2}[A-Z]{3}\d{4})\s+(\d{4})\s+(-?\d+(?:\.\d+)?)\s+([\d,]+)')
    for d,hhmm,stage,flow in pat.findall(text):
        try:
            base=dt.datetime.strptime(d,'%d%b%Y')
            hh=int(hhmm[:2]);mm=int(hhmm[2:])
            if hh==24:base+=dt.timedelta(days=1);hh=0
            local=base.replace(hour=hh,minute=mm,tzinfo=ZoneInfo('America/Chicago'))
            rows.append({'time':local.astimezone(dt.timezone.utc).isoformat(),'stage_ft':float(stage),'cfs':float(flow.replace(',',''))})
        except Exception:pass
    out={'source':url,'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'http_status':status,'series':rows,'records':len(rows),'status':'PARSED' if rows else 'NO_ROWS_PARSED'}
except Exception as e:out={'source':url,'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'http_status':None,'series':[],'records':0,'status':'ACQUISITION_FAILED','error':repr(e)}
(ROOT/'priority_clarendon.json').write_text(json.dumps(out,indent=2))
(ROOT/'priority_tributary_acquisition.json').write_text(json.dumps({'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'routes':LOG,'note':'Metadata/stageflow/ratings are separate NOAA routes, not independent authorities. NWM checkpoint flow is model guidance. Stage-only evidence is never promoted to discharge.'},indent=2))
print('Priority tributary supplemental requests:',len(LOG),'successful:',sum(r['http_status']==200 for r in LOG),'Clarendon rows:',out.get('records'))
