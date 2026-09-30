#!/usr/bin/env python3
"""One-pass release verification using already downloaded evidence.

No additional HTTP calls: acquisitions own network traffic, this stage reads their
immutable raw responses once and reports distinct observation, representation,
and metadata routes without falsely claiming they are independent sensors.
"""
import datetime as dt
import json
import math
import pathlib
import re
from collections import defaultdict

ROOT = pathlib.Path('output')
NOW = lambda: dt.datetime.now(dt.timezone.utc)
PARAMS = {'discharge': '00060', 'stage': '00065'}

def read(path, default=None):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return default

def time_utc(value):
    try:
        t = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return t.astimezone(dt.timezone.utc) if t.tzinfo else None
    except (ValueError, TypeError, OverflowError): return None

def number(value):
    try:
        v = float(value)
        return v if math.isfinite(v) and abs(v) < 1e10 and v not in (-999999, -99999, -9999, -999, 999999, 99999, 9999) else None
    except (ValueError, TypeError): return None

def usgs_points(data, code):
    """Parse legacy IV/DV; DV is verification of published aggregates, not IV."""
    points=[]
    if not isinstance(data,dict): return points
    for ts in data.get('value',{}).get('timeSeries',[]):
        if code not in [str(x.get('value')) for x in ts.get('variable',{}).get('variableCode',[])]: continue
        for block in ts.get('values',[]):
            for p in block.get('value',[]):
                t=time_utc(p.get('dateTime'));v=number(p.get('value'))
                if t and v is not None: points.append((t,v))
    return sorted(set(points))

def ogc_inspect(data, code):
    """Discover OGC feature schema from returned payload; reject mismatched parameter.

    OGC response formats evolve. Record evidence and sample keys; do not coerce
    unknown features into instantaneous observations or silently change units.
    """
    if not isinstance(data,dict): return {'valid':False,'reason':'not JSON object'}
    features=data.get('features')
    if not isinstance(features,list): return {'valid':False,'reason':'no features array','top_keys':list(data)[:15]}
    fields=set();matched=0;dated=0;numeric=0
    for feature in features:
        p=feature.get('properties',{}) if isinstance(feature,dict) else {}
        if not isinstance(p,dict): continue
        fields.update(p)
        flat=json.dumps(p,default=str)
        if re.search(r'(?<!\d)'+re.escape(code)+r'(?!\d)',flat):matched+=1
        if any(time_utc(p.get(k)) for k in ('time','phenomenonTime','phenomenon_time','dateTime','datetime')):dated+=1
        if any(number(p.get(k)) is not None for k in ('value','result','observed_value')):numeric+=1
    return {'valid':True,'features':len(features),'parameter_explicitly_matched':matched,
            'timestamp_recognized':dated,'numeric_value_recognized':numeric,'property_keys':sorted(fields),
            'observation_schema_verified':bool(matched and dated and numeric)}

def nwps_inspect(data, variable):
    if not isinstance(data,dict):return {'valid':False,'reason':'no JSON object'}
    points=[]
    for key in ('observed','forecast'):
        block=data.get(key,{})
        for p in block.get('data',[]) if isinstance(block,dict) else []:
            if not isinstance(p,dict):continue
            t=time_utc(p.get('validTime') or p.get('time') or p.get('dateTime'))
            v=number(p.get('primary') if variable=='stage' else p.get('secondary'))
            if t and v is not None:points.append((key,t,v))
    return {'valid':True,'points':len(points),'observed':sum(p[0]=='observed' for p in points),
            'forecast':sum(p[0]=='forecast' for p in points), 'raw_keys':list(data)[:15]}

def verify(root=ROOT):
    registry=read(pathlib.Path('network_registry.json'),{})
    acq=read(root/'acquisition_summary.json',{})
    noaa=read(root/'audit.json',{})
    cwms=read(root/'usace_series_audit.json',{})
    pairs=read(root/'nwm_pairing_verification.json',{}).get('nodes',{})
    candidates=read(pathlib.Path('config/tributary_candidates.json'),{}).get('nodes',{})
    mappings=read(pathlib.Path('config/usace_series.json'),{}).get('series',[])
    mapping_by_node=defaultdict(list)
    for row in mappings:
        if row.get('approved'):mapping_by_node[row['node']].append(row)
    station_by_lid={r.get('lid'):r for r in noaa.get('stations',[]) if r.get('lid')}
    results={};blockers=[]
    for node in registry.get('reaches',[])+registry.get('junctions',[]):
        nid=node['id'];lid=node.get('lid');sid=str(node.get('usgs') or '')
        record={'name':node.get('name'),'lid':lid,'usgs':sid,'variables':{},'mouth':{},'metadata':{}}
        if lid:
            meta=read(root/'raw/nwps'/lid/'metadata.json')
            ratings=read(root/'raw/nwps'/lid/'ratings.json')
            hefs=list((root/'raw/hefs'/lid).glob('quantiles_*.json')) if (root/'raw/hefs'/lid).exists() else []
            record['metadata']={'NOAA_metadata':isinstance(meta,dict),
                'NOAA_ratings':isinstance(ratings,dict) and bool(ratings.get('data')),
                'NOAA_datum_fields':meta.get('datums') if isinstance(meta,dict) else None,
                'HEFS_quantile_files':len(hefs),
                'HEFS_nonempty':sum(bool((read(f,{}) or {}).get('value_set')) for f in hefs)}
            if not record['metadata']['NOAA_metadata']:
                blockers.append({'node':nid,'variable':'NOAA_metadata','reason':'No valid authoritative NOAA metadata response'})
            if not record['metadata']['NOAA_ratings']:
                blockers.append({'node':nid,'variable':'NOAA_rating','reason':'No populated NOAA rating; cannot derive Q from stage'})
            if not record['metadata']['NOAA_datum_fields']:
                blockers.append({'node':nid,'variable':'NOAA_datum','reason':'No NOAA datum metadata; NAVD88 conversion cannot be independently verified'})
        else:
            record['metadata']={'NOAA':'No registered NWPS identifier; USGS and USACE routes evaluated where mapped'}
        for variable,code in PARAMS.items():
            routes=[]
            # Each route is independently logged, but two representations of the
            # same sensor are NOT counted as independent measurements.
            if lid:
                path=root/'raw/nwps'/lid/'stageflow.json'
                obj=read(path)
                info=nwps_inspect(obj,variable)
                routes.append({'route':'NOAA_NWPS_stageflow','attempted':True,'success':bool(info.get('valid')),
                               'evidence':info,'file':str(path),'sensor_independence':'NOAA'} )
            if sid:
                for route,filename in [('USGS_instantaneous',code+'_legacy.json'),('USGS_OGC',code+'_ogc_continuous.json'),('USGS_daily_aggregate',code+'_legacy_dv.json')]:
                    path=root/'raw/usgs'/sid/filename;obj=read(path)
                    info=ogc_inspect(obj,code) if route=='USGS_OGC' else {'records':len(usgs_points(obj,code))}
                    routes.append({'route':route,'attempted':True,'success':bool(info.get('observation_schema_verified') if route=='USGS_OGC' else info.get('records')),
                                   'evidence':info,'file':str(path),'sensor_independence':'USGS' if route!='USGS_daily_aggregate' else 'USGS_AGGREGATE_NOT_INDEPENDENT'})
            for row in mapping_by_node.get(nid,[]):
                if row['variable']!=variable:continue
                path=root/'raw/usace/series'/nid/(variable+'.json');obj=read(path)
                valid=isinstance(obj,dict) and isinstance(obj.get('values'),list)
                routes.append({'route':'USACE_CWMS_exact_series','attempted':True,'success':bool(valid and obj['values']),
                               'evidence':{'values':len(obj.get('values',[])) if valid else 0,'office':row['office'],'series_id':row['timeseries_id']},
                               'file':str(path),'sensor_independence':'USACE (may relay USGS; see mapping)'})
            if not routes:blockers.append({'node':nid,'variable':variable,'reason':'No verified source identifiers; requires targeted discovery'})
            elif not any(r['success'] for r in routes):blockers.append({'node':nid,'variable':variable,'reason':'All configured observation routes empty, unavailable or invalid'})
            record['variables'][variable]={'routes':routes,'attempted':len(routes),'successful':sum(r['success'] for r in routes)}
        if nid in ('oldriver','morganza','bonnet','davis','caernarvon'):
            operations=[r for r in mapping_by_node.get(nid,[]) if r.get('variable') in ('operation','gate_opening')]
            record['structure_operations']={'approved_exact_series':len(operations),
                'discovery_attempts':sum(1 for r in acq.get('cwms_discovery',[]) if r.get('node')==nid)}
            if not operations:
                blockers.append({'node':nid,'variable':'structure_operations','reason':'No approved exact CWMS operations series; targeted catalog discovery attempted where configured'})
        if nid in candidates:
            c=candidates[nid];pair=pairs.get(nid,{})
            record['mouth']={'upstream_candidates':c.get('usgs_sites',[]),
                'gauge_approved':pair.get('gauge_approved',False),
                'mouth_approved':pair.get('mouth_approved',False),
                'routing_status':pair.get('routing_status','no verified route'),
                'backwater_review_required':pair.get('backwater_review_required',True),
                'mouth_model_status':pair.get('mouth_model_status','unavailable')}
            if not record['mouth']['mouth_approved']:
                blockers.append({'node':nid,'variable':'near_mouth_discharge','reason':'No verified near-mouth NWM mapping or equivalent measured gauge; cannot assume upstream gauge equals mouth'})
        results[nid]=record
    report={'generated_utc':NOW().isoformat(),'network_nodes':len(results),
            'usgs_sites_audited':len(acq.get('usgs',{})),
            'noaa_requests':len(noaa.get('requests',[])),
            'usgs_requests':acq.get('request_count',0),
            'usace_exact_series_attempts':len(cwms.get('requests',[])),
            'stations':results,'blockers':blockers,
            'important_distinction':'Three attempted retrieval routes are not three independent measurements. Upstream gauge-to-mouth equivalence requires evidence.'}
    root.mkdir(exist_ok=True)
    (root/'complete_verification.json').write_text(json.dumps(report,indent=2,default=str))
    print(json.dumps({'nodes':len(results),'blockers':len(blockers),'usgs_sites':report['usgs_sites_audited']},indent=2))
    return report

if __name__=='__main__':verify()
