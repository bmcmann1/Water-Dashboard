#!/usr/bin/env python3
"""Fetch ONLY reviewed CWMS timeseries IDs; never mistake a catalog match for flow."""
import datetime as dt,hashlib,json,pathlib,urllib.parse,urllib.request,urllib.error
P=pathlib.Path; ROOT=P('output'); CONFIG=json.loads(P('config/usace_series.json').read_text()); logs=[]
for row in CONFIG['series']:
    if not row.get('approved'):continue
    if not all(row.get(k) for k in ('node','office','timeseries_id','variable','unit')):raise ValueError('Incomplete approved USACE mapping: '+str(row))
    if row['variable'] not in ('discharge','stage','water_surface_elevation','gate_opening','operation'):raise ValueError('Invalid variable')
    end=dt.datetime.now(dt.timezone.utc);start=end-dt.timedelta(days=7)
    base='https://cwms-data.usace.army.mil/cwms-data/timeseries'
    q={'name':row['timeseries_id'],'office':row['office'],'begin':start.strftime('%Y-%m-%dT%H:%M:%SZ'),'end':end.strftime('%Y-%m-%dT%H:%M:%SZ'),'unit':row['unit']}
    url=base+'?'+urllib.parse.urlencode(q); record={'node':row['node'],'variable':row['variable'],'timeseries_id':row['timeseries_id'],'office':row['office'],'url':url,'retrieved_utc':end.isoformat(),'status':None,'error':None}
    try:
        req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'MississippiHydraulicNetwork/3.0'})
        with urllib.request.urlopen(req,timeout=35) as response: data=response.read(12_000_001);record['status']=response.status
        if len(data)>12_000_000:raise ValueError('12 MB response limit exceeded')
        obj=json.loads(data);record['json_ok']=True;record['value_count']=len(obj.get('values',[])) if isinstance(obj,dict) else None
        record['sha256']=hashlib.sha256(data).hexdigest()
        target=ROOT/'raw/usace/series'/row['node'];target.mkdir(parents=True,exist_ok=True)
        (target/(row['variable']+'.json')).write_bytes(data)
        (target/(row['variable']+'.mapping.json')).write_text(json.dumps(row,indent=2))
    except urllib.error.HTTPError as e:record['status']=e.code;record['error']=str(e)
    except Exception as e:record['error']=repr(e)
    logs.append(record)
(ROOT/'usace_series_audit.json').write_text(json.dumps({'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'approved_mappings':len(logs),'requests':logs,'note':'Only explicitly approved exact CWMS IDs are acquired; empty list is discovery-only, not complete USACE coverage.'},indent=2))
print('USACE exact series attempted:',len(logs),'successful:',sum(x.get('json_ok',False) for x in logs))
