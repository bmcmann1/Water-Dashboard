#!/usr/bin/env python3
"""Conditional, bounded fallback acquisition and evidence grading.

Primary observations are preferred. Reuse downloaded USGS legacy IV responses;
fetch at most two hydrologically named candidates per missing network node.
An upstream gauge is a reference, NEVER automatically a mouth-equivalent inflow.
This script enriches normalized_network.json without modifying original raw data.
"""
import datetime as dt, hashlib, json, math, pathlib, re, urllib.error, urllib.parse, urllib.request

ROOT=pathlib.Path('output'); NOW=dt.datetime.now(dt.timezone.utc)
MAX_BYTES=1_500_000; MAX_PER_NODE=2; MAX_TOTAL_REQUESTS=36
# Curated candidates are *search targets*, not approved mouth-equivalent stations.
CURATED={'ohio':[('03612600','Ohio River at Olmsted, IL')],
         'illinois':[('05587060','Illinois River')],
         'bigmuddy':[('05599500','Big Muddy River')],
         'white':[('07077830','White River')],
         'arkansas':[('07265280','Arkansas River')]}
# Reject tributary candidates that merely happen to be nearby.
RIVER={'ohio':'ohio river','illinois':'illinois river','bigmuddy':'big muddy river',
       'stfrancis':'st francis river','white':'white river','arkansas':'arkansas river',
       'salt':'salt river','forkeddeer':'forked deer river','meramec':'meramec river',
       'kaskaskia':'kaskaskia river','bayousara':'bayou sara'}

def read(path, default=None):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def parse_time(v):
    try:
        t=dt.datetime.fromisoformat(str(v).replace('Z','+00:00'))
        return t.astimezone(dt.timezone.utc) if t.tzinfo else None
    except (TypeError,ValueError):return None

def parse_iv(raw,site):
    result=[]
    for series in raw.get('value',{}).get('timeSeries',[]):
        variable=series.get('variable',{})
        code=str(variable.get('variableCode',[{}])[0].get('value',''))
        unit=variable.get('unit',{}).get('unitCode','')
        if code!='00060' or unit.lower().replace(' ','') not in ('ft3/s','ft^3/s','cfs','m3/s'):continue
        factor=35.3146667 if unit=='m3/s' else 1
        for block in series.get('values',[]):
            for p in block.get('value',[]):
                t=parse_time(p.get('dateTime'))
                try:q=float(p.get('value'))*factor
                except (TypeError,ValueError):continue
                if t and math.isfinite(q) and 0<=q<5_000_000 and q not in (9999,99999):
                    result.append({'time':t.isoformat(),'cfs':round(q,2),'source':'USGS legacy IV','site':site,'qualifiers':p.get('qualifiers',[])})
    return sorted({p['time']:p for p in result}.values(),key=lambda p:p['time'])

def candidate_ok(node,name):
    expected=RIVER.get(node)
    if not expected:return False
    cleaned=re.sub(r'[^a-z0-9]+',' ',name.lower()).strip()
    return expected in cleaned

def acquire(root=ROOT,fetch=None):
    network=read(root/'normalized_network.json',{})
    if not network.get('nodes'):raise ValueError('Normalize primary observations before acquiring fallbacks')
    discovery=read(root/'fallback_discovery.json',{})
    report={'generated_utc':NOW.isoformat(),'nodes':{},'requests':[],'reused_files':0,'bytes_transferred':0,
            'policy':'Verified river name and current discharge establish an upstream reference only; mouth transfer requires independent hydraulic evidence.'}
    requests=0
    for nid,node in network['nodes'].items():
        if node.get('kind')=='mainstem':continue
        # Primary may be in USGS or USACE. Never fetch an optional backup for a fresh primary.
        def fresh(series):
            for p in series:
                t=parse_time(p.get('time'))
                if t and -2<=(NOW-t).total_seconds()/3600<=24:return True
            return False
        primary=any(fresh(s.get('00060',[])) for s in node.get('usgs',{}).values()) or fresh(node.get('usace',{}).get('discharge',[]))
        entry={'primary_available':primary,'candidates':[],'status':'PRIMARY_AVAILABLE_BACKUP_OPTIONAL' if primary else 'SEARCHING'}
        report['nodes'][nid]=entry
        if primary:continue
        choices=CURATED.get(nid,[])[:]
        for c in discovery.get('stations',{}).get(nid,{}).get('alternatives',[]):
            sid=str(c.get('site') or '')
            if sid.isdigit() and candidate_ok(nid,c.get('name') or ''):
                choices.append((sid,c['name']))
        seen=set()
        for sid,name in choices:
            if sid in seen or len(entry['candidates'])>=MAX_PER_NODE:continue
            seen.add(sid)
            if not candidate_ok(nid,name):continue
            item={'site':sid,'name':name,'river_identity_verified':True,'mouth_equivalence_approved':False,
                  'hydraulic_status':'UPSTREAM_REFERENCE_ONLY'}
            path=root/'raw/usgs'/sid/'00060_legacy.json'
            raw=read(path)
            if isinstance(raw,dict):report['reused_files']+=1;item['retrieval']='REUSED_PRIMARY_ACQUISITION'
            elif requests<MAX_TOTAL_REQUESTS:
                url='https://waterservices.usgs.gov/nwis/iv/?'+urllib.parse.urlencode({'format':'json','sites':sid,'parameterCd':'00060','period':'P2D'})
                requests+=1;log={'node':nid,'site':sid,'url':url,'status':None,'bytes':0,'error':None}
                try:
                    if fetch is None:
                        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mississippi-Dashboard/13','Accept':'application/json'}),timeout=12) as resp:
                            data=resp.read(MAX_BYTES+1);log['status']=resp.status
                    else:data=fetch(url);log['status']=200
                    if len(data)>MAX_BYTES:raise ValueError('Response exceeds transfer cap')
                    raw=json.loads(data);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                    log['bytes']=len(data);log['sha256']=hashlib.sha256(data).hexdigest();item['retrieval']='FETCHED'
                except (OSError,ValueError,TimeoutError,urllib.error.URLError) as exc:
                    log['error']=str(exc);item['retrieval']='FAILED_OPTIONAL';raw=None
                report['requests'].append(log);report['bytes_transferred']+=log['bytes']
            else:item['retrieval']='BUDGET_EXHAUSTED'
            observations=parse_iv(raw,sid) if isinstance(raw,dict) else []
            recent=[p for p in observations if (t:=parse_time(p['time'])) and -2<=(NOW-t).total_seconds()/3600<=24]
            item['fresh_records']=len(recent)
            if recent:
                latest=recent[-1];item['latest']=latest;item['hydraulic_status']='VERIFIED_UPSTREAM_REFERENCE_NOT_MOUTH'
                # Display on this tributary's own hydrograph, never silently count at mouth.
                node.setdefault('fallback_usgs',{})[sid]=observations[-192:]
                node.setdefault('fallback_references',[]).append(item)
            entry['candidates'].append(item)
        entry['status']='UPSTREAM_REFERENCE_AVAILABLE' if any(x['fresh_records'] for x in entry['candidates']) else 'NO_VERIFIED_CURRENT_ALTERNATIVE'
    (root/'fallback_acquisition.json').write_text(json.dumps(report,indent=2))
    (root/'normalized_network.json').write_text(json.dumps(network,separators=(',',':')))
    print(json.dumps({'fallback_requests':requests,'reused':report['reused_files'],'bytes':report['bytes_transferred'],
                      'fresh_upstream_references':sum(x['status']=='UPSTREAM_REFERENCE_AVAILABLE' for x in report['nodes'].values())}))
    return report
if __name__=='__main__':acquire()
