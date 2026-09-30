"""Auditable, conservative quasi-steady continuity on ordered Mississippi reaches."""
import datetime as dt

def timestamp(value):
    try:
        t=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return t.astimezone(dt.timezone.utc) if t.tzinfo else None
    except (ValueError,TypeError): return None

def solve(nodes,order,junctions,generated_utc,max_gap_hours=24,approved_laterals=None):
    """Return per-reach results and explicit audit. Missing lateral is NEVER zero.

    approved_laterals: optional IDs for which an upstream gauge has been verified
    representative of the actual junction. An explicit node-level
    `mouth_equivalence_approved` flag also authorizes a lateral.
    """
    approved=set(approved_laterals or [])
    by_parent={}
    for j in junctions:by_parent.setdefault(j['parent'],[]).append(j)
    result={}; audit=[]; previous=None; now=timestamp(generated_utc)
    for nid in order:
        n=nodes[nid]; obs=n.get('current_discharge'); terms=[]; missing=[]; reasons=[]
        for j in by_parent.get(nid,[]):
            ident=j['id']; source=nodes.get(ident,{})
            q=source.get('current_discharge'); authorized=(ident in approved or source.get('mouth_equivalence_approved',False))
            if q is None or not authorized:
                missing.append(ident); reasons.append({'node':ident,'reason':'no_fresh_discharge' if not q else 'unverified_upstream_to_mouth_transfer'})
                continue
            sign=1 if j['kind']=='in' else -1
            terms.append({'id':ident,'sign':sign,'cfs':q['cfs'],'source':q.get('source'),'time':q.get('time'),'role':'approved_mouth_equivalent'})
        upstream=result.get(previous) if previous else None
        valid=upstream is not None and upstream.get('cfs') is not None and upstream['status'] in ('observed','continuity')
        times=[timestamp(x.get('time')) for x in terms]
        if upstream and upstream.get('anchor_time'):times.append(timestamp(upstream['anchor_time']))
        if obs and valid:times.append(timestamp(obs.get('time')))
        if now and any(t is None or abs((now-t).total_seconds())>24*3600 for t in times):
            reasons.append({'reason':'stale_or_invalid_time'}); valid=False
        if times and all(times) and (max(times)-min(times)).total_seconds()>max_gap_hours*3600:
            reasons.append({'reason':'time_misalignment'});valid=False
        expected=upstream['cfs']+sum(t['sign']*t['cfs'] for t in terms) if valid and not missing else None
        if expected is not None and expected<0:reasons.append({'reason':'negative_continuity_result'});expected=None
        if obs:
            item={'status':'observed','cfs':obs['cfs'],'anchor_time':obs.get('time'),'expected_cfs':expected,'residual_cfs':obs['cfs']-expected if expected is not None else None}
        elif expected is not None:
            item={'status':'continuity','cfs':expected,'anchor_time':upstream.get('anchor_time')}
        else:
            item={'status':'partial' if valid else 'unbounded','cfs':None,'anchor_time':None}
        item.update({'upstream_id':previous,'terms':terms,'missing':missing,'reasons':reasons})
        result[nid]=item
        audit.append({'node':nid,**item})
        previous=nid
    return result,audit
