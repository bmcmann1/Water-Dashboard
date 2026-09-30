#!/usr/bin/env python3
"""Build a single offline dashboard with generalized geographic network and provenance."""
import json, pathlib, datetime as dt, math
P=pathlib.Path
D=json.loads(P('output/normalized_network.json').read_text())
QC=json.loads(P('output/qc_report.json').read_text())
REG=json.loads(P('network_registry.json').read_text())
GEO=json.loads(P('config/geography.json').read_text())
BASE=json.loads(P('config/flow_baselines.json').read_text())
site=P('site');site.mkdir(exist_ok=True)
parents={n['id']:n.get('parent') for n in REG['junctions']}
order=[n['id'] for n in REG['reaches']]
# Compact the public HTML payload; full raw/normalized evidence stays in the audit artifact.
compact={'generated_utc':D['generated_utc'],'nodes':{},'coverage':D['coverage'],'plausibility_checks':D.get('plausibility_checks',[]),'order':order,'parents':parents,'geography':GEO,'baselines':BASE['baselines']}
for nid,o in D['nodes'].items():
    n={k:o.get(k) for k in ('id','name','kind','noaa_lid','usgs_candidates','caveats','nwm','nwm_verification')}
    n['series']={}
    for label,series in [('NOAA observed stage',o.get('noaa',{}).get('observed',[])),('NOAA official stage forecast',o.get('noaa',{}).get('forecast',[]))]:
        if series:n['series'][label]=[{'time':p['time'],'value':p['value'],'unit':p.get('unit','')} for p in series]
    for sid,params in o.get('usgs',{}).items():
        for code,series in params.items():
            if series:n['series'][f'USGS {sid} '+{'00060':'Discharge','00065':'Gage height','63160':'Water-surface elevation (NAVD88)'}.get(code,code)]=[{'time':p['time'],'value':p['value'],'unit':p.get('unit','')} for p in series]
    for var,series in o.get('usace',{}).items():
        if series:n['series']['USACE '+var.replace('_',' ').title()]=[{'time':p['time'],'value':p['value'],'unit':p.get('unit','')} for p in series]
    # NWM guidance is kept separate from measured USGS/USACE Q.
    n['nwm']=o.get('nwm',{})
    n['hefs']=o.get('noaa',{}).get('hefs_parameters',[])
    compact['nodes'][nid]=n
# Select only a contemporary measured discharge; never convert stage to Q or use stale observations.
now=dt.datetime.fromisoformat(D['generated_utc'].replace('Z','+00:00'))
for nid,n in compact['nodes'].items():
    q=[]
    for label,series in n['series'].items():
        if not ('Discharge' in label or label=='USACE Discharge'):continue
        if not series:continue
        a=series[-1]
        try:
            t=dt.datetime.fromisoformat(a['time'].replace('Z','+00:00'))
            if not (-2 <= (now-t).total_seconds()/3600 <=24):continue
            unit=str(a.get('unit','')).lower()
            v=float(a['value'])
            if 'm3' in unit or 'm³' in unit or 'cms' in unit:v*=35.3146667
            elif 'cfs' not in unit and 'ft3' not in unit and 'ft³' not in unit:continue
            if math.isfinite(v) and v>=0:q.append({'cfs':round(v),'source':label,'time':a['time']})
        except (ValueError,KeyError,TypeError):continue
    # Prefer contemporaneous USGS Q; USACE is alternative. Do not sum co-located stations.
    q.sort(key=lambda x:(not x['source'].startswith('USGS'),x['time']))
    n['current_discharge']=q[0] if q else None
# Flow widths are observed only at nodes with valid Q. No fabricated flow on unknown reaches.
compact['map_note']='Generalized geographic station layout; not surveyed river centerlines. Widths represent fresh measured discharge only, not an interpolated hydraulic solution.'
payload=json.dumps(compact,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
page=P('scripts/dashboard_template.html').read_text().replace('__PAYLOAD__',payload)
(site/'index.html').write_text(page)
# Publish only the self-contained page; archive has the full QC and normalized JSON.
print('Built offline geographic dashboard:',len(compact['nodes']),'nodes; bytes:',(site/'index.html').stat().st_size)
