#!/usr/bin/env python3
"""Reconcile priority tributary inflows using measured flow, lower-river stage checks,
and bounded NOAA NWM checkpoint guidance.

The script never converts stage to discharge.  Stage is used only as a hydraulic
consistency/backwater diagnostic.  Every inferred/model-assisted value carries an
explicit provenance class and evidence list.
"""
from __future__ import annotations
import datetime as dt, json, math, pathlib, re, statistics
from zoneinfo import ZoneInfo

P=pathlib.Path; OUT=P('output'); NOW=dt.datetime.now(dt.timezone.utc)
MAX_AGE_H=24
POL={}
NET={}


def tparse(v):
    try:
        x=dt.datetime.fromisoformat(str(v).replace('Z','+00:00'))
        return x.astimezone(dt.timezone.utc) if x.tzinfo else None
    except (TypeError,ValueError,OverflowError): return None

def isfresh(t,max_age=MAX_AGE_H):
    z=tparse(t); return bool(z and -2 <= (NOW-z).total_seconds()/3600 <= max_age)

def cfs(v,u):
    try: x=float(v)
    except (TypeError,ValueError): return None
    if not math.isfinite(x) or x<0:return None
    s=str(u or '').lower().replace(' ','')
    if s in ('cfs','ft3/s','ft^3/s','ft³/s'):return x
    if s in ('kcfs','kft3/s','kft³/s'):return x*1000
    if s in ('cms','m3/s','m³/s'):return x*35.3146667
    return None

def latest(series):
    good=[x for x in series if tparse(x.get('time'))]
    return max(good,key=lambda x:tparse(x['time'])) if good else None

def usgs_q(node,site):
    arr=NET['nodes'].get(node,{}).get('usgs',{}).get(site,{}).get('00060',[])
    out=[]
    for x in arr:
        q=cfs(x.get('value'),x.get('unit'))
        if q is not None:out.append({'time':x['time'],'cfs':q,'source':f'USGS {site} observed discharge','source_class':'observed'})
    return out

def usgs_stage(node,site):
    arr=NET['nodes'].get(node,{}).get('usgs',{}).get(site,{}).get('00065',[])
    return [{'time':x['time'],'value':float(x['value']),'source':f'USGS {site} stage'} for x in arr if tparse(x.get('time'))]

def load(path):
    try:return json.loads(P(path).read_text())
    except (OSError,ValueError):return None

def priority_stage(lid):
    obj=load(OUT/'raw/priority'/lid/'stage_nwps_stageflow.json') or load(OUT/'raw/nwps'/lid/'stageflow.json')
    out=[]
    if not isinstance(obj,dict):return out
    for x in (obj.get('observed') or {}).get('data',[]):
        if not isinstance(x,dict):continue
        try:v=float(x.get('primary'));tt=tparse(x.get('validTime'))
        except (TypeError,ValueError):continue
        if tt and math.isfinite(v) and -100<v<2000:out.append({'time':tt.isoformat(),'value':v,'source':f'NOAA NWPS {lid} observed stage'})
    return out

def _find_units(obj):
    vals=[]
    def walk(x,depth=0):
        if depth>5:return
        if isinstance(x,dict):
            for k,v in x.items():
                if 'unit' in k.lower() and isinstance(v,str):vals.append(v)
                elif isinstance(v,(dict,list)):walk(v,depth+1)
        elif isinstance(x,list):
            for v in x[:8]:walk(v,depth+1)
    walk(obj);return vals

def priority_observed_flow(lid):
    """Extract NOAA secondary flow ONLY when payload metadata proves flow units."""
    obj=load(OUT/'raw/priority'/lid/'stage_nwps_stageflow.json') or load(OUT/'raw/nwps'/lid/'stageflow.json')
    if not isinstance(obj,dict):return []
    units=_find_units(obj)
    flow_unit=next((u for u in units if cfs(1,u) is not None),None)
    if not flow_unit:return []
    out=[]
    for x in (obj.get('observed') or {}).get('data',[]):
        if not isinstance(x,dict):continue
        val=None
        for k in ('secondary','flow','discharge','streamflow'):
            if x.get(k) is not None: val=x[k];break
        if isinstance(val,dict): val=val.get('value')
        q=cfs(val,flow_unit);tt=tparse(x.get('validTime'))
        if q is not None and tt:out.append({'time':tt.isoformat(),'cfs':q,'source':f'NOAA NWPS {lid} observed flow','source_class':'observed'})
    return out

def priority_nwm(lid):
    obj=load(OUT/'raw/priority'/lid/'nwm_analysis_assimilation.json')
    if not isinstance(obj,dict):return []
    found=[]
    def walk(x,unit=None,depth=0):
        if depth>6:return
        if isinstance(x,dict):
            unit=x.get('units') or x.get('unit') or unit
            if isinstance(x.get('data'),list):
                for p in x['data']:
                    if not isinstance(p,dict):continue
                    tm=p.get('validTime') or p.get('time')
                    v=p.get('flow',p.get('streamflow',p.get('value')))
                    if isinstance(v,dict):v=v.get('value')
                    q=cfs(v,unit)
                    if q is not None and tparse(tm):found.append({'time':tparse(tm).isoformat(),'cfs':q,'source':f'NOAA NWM analysis at {lid}','source_class':'modeled'})
            for v in x.values():
                if isinstance(v,(dict,list)):walk(v,unit,depth+1)
        elif isinstance(x,list):
            for v in x[:20]:walk(v,unit,depth+1)
    walk(obj)
    return sorted({x['time']:x for x in found}.values(),key=lambda x:x['time'])

def checkpoint_flow(lid):
    obs=priority_observed_flow(lid)
    return obs if obs else priority_nwm(lid)

def stage_change(series,hours=12):
    if len(series)<2:return {'status':'insufficient_stage'}
    s=sorted(series,key=lambda x:tparse(x['time']));end=s[-1];te=tparse(end['time']);target=te-dt.timedelta(hours=hours)
    start=min(s,key=lambda x:abs((tparse(x['time'])-target).total_seconds()))
    elapsed=(te-tparse(start['time'])).total_seconds()/3600
    if elapsed<max(2,hours*.4):return {'status':'insufficient_span'}
    delta=end['value']-start['value']
    return {'status':'ok','delta_ft':round(delta,3),'hours':round(elapsed,2),'rate_ft_per_hr':round(delta/elapsed,4),'latest_time':end['time']}

def paired_residual(up,down,max_gap_h=2):
    """Use same-time/small-gap pairs for model states; empirical lag for observations."""
    if not up or not down:return None
    classes={x.get('source_class') for x in up+down}
    best=None
    lags=[0] if classes=={'modeled'} else list(range(0,73,3))
    for lag in lags:
        vals=[]
        for d in down:
            td=tparse(d['time']);target=td-dt.timedelta(hours=lag)
            u=min(up,key=lambda x:abs((tparse(x['time'])-target).total_seconds()),default=None)
            if not u:continue
            gap=abs((tparse(u['time'])-target).total_seconds())/3600
            if gap<=max_gap_h:vals.append((u,d))
        if not vals:continue
        residuals=[d['cfs']-u['cfs'] for u,d in vals]
        score=(len(vals),-statistics.pstdev(residuals) if len(residuals)>1 else 0)
        if best is None or score>best[0]:best=(score,lag,vals,residuals)
    if not best:return None
    _,lag,vals,residuals=best;u,d=vals[-1];r=d['cfs']-u['cfs']
    return {'cfs':r,'time':d['time'],'lag_hours':lag,'pair_count':len(vals),'upstream_cfs':u['cfs'],'downstream_cfs':d['cfs'],'upstream_source':u['source'],'downstream_source':d['source'],'residual_pstdev_cfs':round(statistics.pstdev(residuals)) if len(residuals)>1 else None,'source_class':'observed' if {u.get('source_class'),d.get('source_class')}=={'observed'} else 'modeled'}

def result(node,status,cfs_value=None,time=None,method=None,source_class=None,evidence=None,checks=None,confidence=None,usable=False,notes=None):
    return {'node':node,'status':status,'usable_for_continuity':bool(usable),'cfs':round(cfs_value) if cfs_value is not None and cfs_value>=0 else None,'time':time,'method':method,'source_class':source_class,'evidence':evidence or [],'checks':checks or [],'confidence':confidence,'notes':notes or []}

# White River: direct Clarendon flow is the measured quantitative anchor; lower stage and NWM are checks.
def white():
    clar=load(OUT/'priority_clarendon.json') or {};series=clar.get('series',[])
    qseries=[{'time':x['time'],'cfs':x['cfs'],'source':'USACE SWL White River at Clarendon (NPTA4)','source_class':'observed'} for x in series if x.get('cfs') is not None]
    base=latest(qseries)
    if not base or not isfresh(base['time']):
        dv=latest(usgs_q('white','07077000'));base=dv if dv and isfresh(dv['time']) else None
    checks=[]
    for lid in ('NOGA4','SCHA4'):
        checks.append({'checkpoint':lid,'stage_12h':stage_change(priority_stage(lid),12),'nwm_latest':latest(priority_nwm(lid))})
    if not base:return result('white','NO_FRESH_QUANTITATIVE_ANCHOR',method='multistation_hydraulic',checks=checks,notes=['Stage is diagnostic only; it is not converted to discharge.'])
    mouth_model=latest(priority_nwm('SCHA4'));ratio=None
    if mouth_model and mouth_model['cfs']>0:ratio=base['cfs']/mouth_model['cfs']
    confidence='moderate-high' if ratio is not None and .7<=ratio<=1.3 else 'moderate'
    return result('white','RECONCILED',base['cfs'],base['time'],'clarendon_plus_lower_stage_nwm_checks','observed_reconciled',[base],checks,confidence,True,[f'St Charles NWM comparison ratio observed_anchor/model={ratio:.2f}' if ratio else 'No validated numerical NWM comparison available.','Lower White floodplain/backwater uncertainty retained; stage checkpoints do not create flow.'])

# St Francis: bounding Mississippi mainstem residual, observed if available, otherwise same-model NWM residual.
def stfrancis():
    up=checkpoint_flow('HEEA4');dn=checkpoint_flow('MHOM6');r=paired_residual(up,dn)
    if not r:return result('stfrancis','NO_PAIRED_BOUNDING_FLOW',method='mainstem_residual_only',checks=[{'HEEA4':len(up),'MHOM6':len(dn)}])
    if r['cfs']<=0:return result('stfrancis','NONPOSITIVE_RESIDUAL',method='mainstem_residual_only',source_class=r['source_class'],evidence=[r],confidence='low',usable=False,notes=['Negative/zero residual can reflect routing, storage, measurement/model error or unresolved laterals; it is not reported as negative tributary flow.'])
    klass='mainstem_mass_balance_inferred' if r['source_class']=='observed' else 'nwm_mainstem_residual'
    return result('stfrancis','RECONCILED',r['cfs'],r['time'],klass,klass,[r],confidence='moderate' if r['source_class']=='observed' else 'screening-model',usable=True,notes=['Represents St. Francis-area net lateral contribution, including any unresolved small laterals/storage between the bounding Mississippi checkpoints.'])

# Meramec: Eureka is quantitative observation; lower stages and a St Louis-Herculaneum NWM residual reconcile it.
def meramec():
    eu=latest(usgs_q('meramec','07019000'));eufresh=bool(eu and isfresh(eu['time']))
    model_res=paired_residual(priority_nwm('EADM7'),priority_nwm('HRCM7'))
    checks=[{'Arnold_stage_12h':stage_change(priority_stage('ARNM7') or usgs_stage('meramec','07019300'),12)}, {'Herculaneum_stage_12h':stage_change(priority_stage('HRCM7'),12)}, {'mainstem_model_residual':model_res}]
    if eufresh:
        ratio=None
        if model_res and model_res['cfs']>0:ratio=eu['cfs']/model_res['cfs']
        confidence='moderate-high' if ratio is not None and .6<=ratio<=1.6 else 'moderate'
        return result('meramec','RECONCILED',eu['cfs'],eu['time'],'eureka_observed_plus_lower_stage_mainstem_reconciliation','observed_reconciled',[eu]+([model_res] if model_res else []),checks,confidence,True,[f'Eureka/mainstem-residual ratio={ratio:.2f}' if ratio else 'Herculaneum has no observed rating flow; NWM same-model St Louis-Herculaneum residual is used only as a cross-check.','Arnold/Herculaneum stages are diagnostics for lower-river/backwater changes.'])
    if model_res and model_res['cfs']>0 and isfresh(model_res['time']):
        return result('meramec','MODEL_FALLBACK',model_res['cfs'],model_res['time'],'st_louis_to_herculaneum_nwm_residual','modeled_mainstem_residual',[model_res],checks,'screening-model',True,['Used only because fresh Eureka discharge was unavailable.'])
    return result('meramec','NO_FRESH_QUANTITATIVE_ANCHOR',method='upstream_plus_mainstem_reconciliation',checks=checks)

# Arkansas: validated parsed Wilbur D. Mills total release.
def arkansas():
    obj=load(OUT/'mills_dam_acquisition.json') or {};rows=obj.get('series',[]);p=latest(rows)
    if p and isfresh(p.get('time')) and p.get('total_release_cfs') is not None:
        return result('arkansas','RECONCILED',p['total_release_cfs'],p['time'],'wilbur_d_mills_total_release','observed_controlled_release',[p],confidence='high-at-structure',usable=True,notes=['Represents downstream-most control-structure release; lower-channel travel/storage uncertainty remains.'])
    return result('arkansas','NO_FRESH_MILLS_RELEASE',method='wilbur_d_mills_total_release',evidence=[obj])

def run():
    global POL,NET,NOW
    NOW=dt.datetime.now(dt.timezone.utc)
    POL=json.loads(P('config/priority_tributary_policy.json').read_text())
    NET=json.loads((OUT/'normalized_network.json').read_text())
    res={'white':white(),'stfrancis':stfrancis(),'meramec':meramec(),'arkansas':arkansas()}
    summary={'generated_utc':NOW.isoformat(),'policy_version':POL.get('version'),'results':res,'usable_count':sum(v['usable_for_continuity'] for v in res.values()),'warning':'Stage-only observations are diagnostics and are never transformed into discharge.'}
    (OUT/'priority_tributary_reconciliation.json').write_text(json.dumps(summary,indent=2))
    print('Priority tributary reconciliations:',{k:v['status'] for k,v in res.items()})
    return summary

if __name__=='__main__':run()
