#!/usr/bin/env python3
"""NWM/USGS verification after acquisition; never invent or auto-approve reach IDs.

STEP 1: Reuse downloaded NWM series and USGS legacy observations (zero extra API calls).
STEP 2: Align UTC observations with nearest NWM analysis within 60 minutes.
STEP 3: Report signed bias, MAE, RMSE, percent bias, and high-flow subset.
STEP 4: Check approved gauge/mouth metadata and route evidence, and flag
        low-gradient/backwater tributaries for separate hydraulic review.
STEP 5: Publish a compact status report; corrections are DIAGNOSTIC ONLY.

A matching location and good fit do not prove that near-mouth modeled flow is
accurate. Neither a candidate reach nor an upstream gauge is a measured mouth Q.
"""
import csv, datetime as dt, json, math, pathlib, statistics
ROOT=pathlib.Path(__file__).resolve().parent.parent
BACKWATER={'illinois','ohio','stfrancis','white','arkansas','yazoo','bigblack','bayousara','loosahatchie','wolf'}

def read(path,default=None):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def stamp(s):
    try:
        x=dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return x.astimezone(dt.timezone.utc) if x.tzinfo else None
    except (ValueError,TypeError,OverflowError):return None

def cfs(value,unit):
    try:
        v=float(value);u=str(unit or '').lower().replace(' ','')
        if not math.isfinite(v) or v<0:return None
        if u in ('cfs','ft3/s','ft³/s','ft^3/s'):return v
        if u in ('cms','m3/s','m³/s','m^3/s'):return v*35.314666721
    except (ValueError,TypeError):pass
    return None

def match(observed,modeled,tolerance_minutes=60):
    """Two-pointer UTC alignment, O(n+m), no interpolated observations."""
    o=sorted((x for p in observed if (x:=(stamp(p.get('time')),cfs(p.get('value'),p.get('unit'))))[0] and x[1] is not None),key=lambda x:x[0])
    m=sorted((x for p in modeled if (x:=(stamp(p.get('time')),cfs(p.get('value'),p.get('unit'))))[0] and x[1] is not None),key=lambda x:x[0])
    out=[];j=0;tol=tolerance_minutes*60
    for t,v in o:
        while j+1<len(m) and m[j+1][0]<=t:j+=1
        candidates=m[max(0,j-1):min(len(m),j+2)]
        if not candidates:continue
        nearest=min(candidates,key=lambda x:abs((x[0]-t).total_seconds()))
        if abs((nearest[0]-t).total_seconds())<=tol:out.append((t,v,nearest[1]))
    return out

def metrics(pairs):
    if not pairs:return {'matched_points':0,'status':'no overlapping comparable discharge'}
    errors=[m-o for _,o,m in pairs];obs=[o for _,o,_ in pairs]
    high_cut=sorted(obs)[max(0,math.ceil(.9*len(obs))-1)]
    high=[m-o for _,o,m in pairs if o>=high_cut]
    return {'matched_points':len(pairs),'period_start_utc':pairs[0][0].isoformat(),
        'period_end_utc':pairs[-1][0].isoformat(),
        'mean_bias_cfs':round(statistics.mean(errors),2),
        'mae_cfs':round(statistics.mean(map(abs,errors)),2),
        'rmse_cfs':round(math.sqrt(statistics.mean(e*e for e in errors)),2),
        'percent_bias':round(100*sum(errors)/sum(obs),2) if sum(obs)>0 else None,
        'high_flow_threshold_cfs':round(high_cut,2),
        'high_flow_matched_points':len(high),
        'high_flow_mean_bias_cfs':round(statistics.mean(high),2) if high else None,
        'status':'diagnostic only' if len(pairs)<24 else 'statistics available; engineering review required'}

def run(root=ROOT):
    config=read(root/'config/nwm_reach_pairs.json',{}).get('pairs',{})
    model=read(root/'output/nwm_normalized.json',{}).get('nodes',{})
    discovery=read(root/'output/nwm_crosswalk_candidates.json',{})
    candidates=discovery.get('nodes',{});meta=discovery.get('reach_metadata',{})
    output={};summary=[]
    for name,cfg in config.items():
        gauge=cfg.get('gauge_reach_id');mouth=cfg.get('mouth_reach_id');site=cfg.get('usgs_site')
        result={'usgs_site':site,'gauge_reach_id':gauge,'mouth_reach_id':mouth,
            'gauge_approved':bool(gauge and cfg.get('gauge_match_verified')),
            'mouth_approved':bool(mouth and cfg.get('mouth_match_verified')),
            'candidate_gauge_reach':candidates.get(name,{}).get('gauge_candidate'),
            'candidate_mouth_count':len(candidates.get(name,{}).get('mouth_candidates',[])),
            'backwater_review_required':name in BACKWATER,
            'routing_status':'not independently verified',
            'mouth_model_status':'unavailable', 'validation':{'matched_points':0,'status':'not evaluated'}}
        # Metadata fields differ across NWM versions. Preserve evidence for human
        # inspection rather than guessing that a proximity match proves routing.
        if gauge and mouth and gauge in meta and mouth in meta:
            result['routing_evidence']={'gauge':meta[gauge],'mouth':meta[mouth]}
            result['routing_status']='metadata available; confirm downstream connectivity and no intervening diversion'
        series=model.get(name,{})
        if result['gauge_approved'] and site:
            raw=read(root/'output/raw/usgs'/str(site)/'00060_legacy.json',{})
            observed=[]
            for ts in raw.get('value',{}).get('timeSeries',[]):
                unit=(ts.get('variable',{}).get('unit') or {}).get('unitCode')
                for block in ts.get('values',[]):
                    for p in block.get('value',[]):
                        observed.append({'time':p.get('dateTime'),'value':p.get('value'),'unit':unit})
            m=series.get('gauge_analysis_assimilation',{}).get('series',[])
            result['validation']=metrics(match(observed,m))
        if result['mouth_approved']:
            mouth_series=series.get('mouth_analysis_assimilation',{}).get('series',[])
            forecast=series.get('mouth_short_range',{}).get('series',[])
            result['mouth_model_status']='analysis available' if mouth_series else 'approved reach; analysis unavailable'
            result['mouth_forecast_points']=len(forecast)
            # A model difference is NOT observed lateral inflow; store only
            # matched modeled gauge/mouth times and no automatically corrected Q.
            gm=series.get('gauge_analysis_assimilation',{}).get('series',[])
            both=match(gm,mouth_series)
            result['modeled_mouth_minus_gauge_cfs']=round(both[-1][2]-both[-1][1],2) if both else None
        result['publishable_model_guidance']=bool(result['mouth_approved'] and
            result['mouth_model_status']=='analysis available')
        result['validation_qualifies_mouth']=False
        result['auto_bias_correction_applied']=False
        result['review_notes']='Gauge fit is diagnostic; mouth routing, downstream drainage and backwater require separate review.'
        output[name]=result
        summary.append({k:result.get(k) for k in ('usgs_site','gauge_reach_id','mouth_reach_id','gauge_approved','mouth_approved','routing_status','backwater_review_required','mouth_model_status','publishable_model_guidance') }|{'tributary':name,'matched_points':result['validation']['matched_points'],'percent_bias':result['validation'].get('percent_bias')})
    out=root/'output';out.mkdir(exist_ok=True)
    report={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'policy':'No candidate auto-approval, no automatic bias transfer, no NWM substitution for measured discharge.',
        'nodes':output}
    (out/'nwm_pairing_verification.json').write_text(json.dumps(report,indent=2))
    with (out/'nwm_pairing_verification.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]) if summary else ['tributary']);w.writeheader();w.writerows(summary)
    print('NWM pairing verification:',len(output),'tributaries;',sum(v['validation']['matched_points']>0 for v in output.values()),'with paired observations')
    return report
if __name__=='__main__':run()
