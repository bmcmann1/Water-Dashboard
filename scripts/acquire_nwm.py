#!/usr/bin/env python3
"""Acquire only explicitly verified NOAA NWM reaches. No national NetCDF downloads.

STEPS
  1. Read approved gauge/near-mouth NWM reach IDs from config.
  2. Deduplicate requests shared by tributaries and request analysis + short range.
  3. Validate metadata and time/value/unit fields; do not invent model readings.
  4. Save compact normalized time series and request audit for later QC.

NWM is model guidance, not USGS observations or an official NWS forecast.
An empty mapping file is a deliberate safe no-op, not evidence of zero flow.
"""
import datetime as dt, json, pathlib, urllib.request, urllib.error, time, math
P=pathlib.Path; OUT=P('output');OUT.mkdir(exist_ok=True)
CONF=json.loads(P('config/nwm_reach_pairs.json').read_text())['pairs']
BASE='https://api.water.noaa.gov/nwps/v1/reaches/'
AUDIT=[]; CACHE={}
def fetch(reach,product):
    key=(reach,product)
    if key in CACHE:return CACHE[key]
    url=BASE+str(reach)+'/streamflow?series='+product
    record={'reach_id':reach,'product':product,'url':url,'status':None,'error':None}
    result=None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mississippi-Hydraulic-Network/3.0','Accept':'application/json'}),timeout=25) as r:
                record['status']=r.status;raw=r.read(3_000_001)
            if len(raw)>3_000_000:raise ValueError('NWM response exceeds 3 MB')
            result=json.loads(raw);break
        except (urllib.error.URLError,ValueError,TimeoutError) as e:
            record['error']=str(e)
            if attempt<2:time.sleep(2**attempt)
    AUDIT.append(record);CACHE[key]=result
    return result

def parse(obj):
    """Accept only known NWPS reach streamflow fields; unknown schema is audited, not guessed."""
    if not isinstance(obj,dict):return []
    # NWPS reach payloads can wrap a configuration in a `series` object/list.
    found=[]
    def walk(x,depth=0):
        if depth>5:return
        if isinstance(x,dict):
            if isinstance(x.get('data'),list):
                unit=x.get('units') or x.get('unit') or obj.get('units')
                for item in x['data']:
                    if not isinstance(item,dict):continue
                    t=item.get('validTime') or item.get('time')
                    val=item.get('flow') if item.get('flow') is not None else (item.get('streamflow') if item.get('streamflow') is not None else item.get('value'))
                    if isinstance(val,dict):val=val.get('value')
                    try:
                        v=float(val);stamp=dt.datetime.fromisoformat(str(t).replace('Z','+00:00'))
                        if stamp.tzinfo and math.isfinite(v) and v>=0 and unit:
                            found.append({'time':stamp.isoformat(),'value':v,'unit':str(unit),'source':'NOAA NWM'})
                    except (TypeError,ValueError,OverflowError):pass
            for k,v in x.items():
                if k!='data' and isinstance(v,(dict,list)):walk(v,depth+1)
        elif isinstance(x,list):
            for v in x[:15]:walk(v,depth+1)
    walk(obj)
    return sorted({x['time']:x for x in found}.values(),key=lambda x:x['time'])

nodes={}
for node,cfg in CONF.items():
    series={}
    for role in ('gauge','mouth'):
        reach=cfg.get(role+'_reach_id')
        if not (reach and cfg.get(role+'_match_verified')):continue
        for product in ('analysis_assimilation','short_range'):
            data=parse(fetch(reach,product))
            if data:series[role+'_'+product]={'reach_id':reach,'series':data,'label':'modeled','verified_match':True}
    if series:nodes[node]=series
result={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'nodes':nodes,'mapped_nodes':len(nodes),
        'warning':'No unverified NWM IDs; NWM model guidance is not an observation.'}
(OUT/'nwm_normalized.json').write_text(json.dumps(result,separators=(',',':')))
(OUT/'nwm_request_audit.json').write_text(json.dumps(AUDIT,indent=2))
print('NWM approved tributaries:',len(nodes),'unique requests:',len(CACHE))
