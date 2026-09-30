#!/usr/bin/env python3
"""ONE-TIME / ON-DEMAND NWM CROSSWALK DISCOVERY; never auto-approve a match.

STEP 1: Reuse existing USGS IDs and optional gauge/mouth coordinates from config.
STEP 2: Fetch NOAA gauge metadata ONCE per unique USGS ID. Its `reachId` is
        an authoritative gauge-linked candidate, not a verified mouth match.
STEP 3: For optional independently surveyed mouth coordinates, query only a
        tiny NOAA NWM GIS bounding box; record candidates, never nearest=truth.
STEP 4: Validate candidate reach IDs with NOAA's individual reach endpoint;
        record routing topology and a tiny analysis sample for manual review.
STEP 5: Write audit JSON/CSV only. No automated mutation of approved config.

Network I/O: no nationwide hydrofabric download; requests deduplicated, retries
bounded, GIS discovery disabled without independently verified coordinates.
"""
import argparse, csv, datetime as dt, json, pathlib, time, urllib.error, urllib.parse, urllib.request

ROOT=pathlib.Path(__file__).resolve().parent.parent
BASE='https://api.water.noaa.gov/nwps/v1/'
GIS='https://mapservices.weather.noaa.gov/vector/rest/services/obs/NWM_Stream_Analysis/MapServer/5/query'
HEAD={'User-Agent':'Mississippi-Hydraulic-Network/3.1 (crosswalk-audit)','Accept':'application/json'}

def request(url, audit, cap=1_500_000):
    row={'url':url,'retrieved_utc':None,'http_status':None,'error':None}
    for attempt in range(2):
        try:
            req=urllib.request.Request(url,headers=HEAD)
            with urllib.request.urlopen(req,timeout=20) as resp:
                row['http_status']=resp.status
                raw=resp.read(cap+1)
            if len(raw)>cap:raise ValueError('Response exceeds bounded size')
            obj=json.loads(raw)
            row['retrieved_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
            audit.append(row)
            return obj
        except (urllib.error.URLError,TimeoutError,ValueError) as exc:
            row['error']=str(exc)
            if attempt==0:time.sleep(1)
    audit.append(row)
    return None

def gauge_match(payload, usgs):
    """NOAA documents `usgsId` and `reachId`; require exact USGS identity."""
    if not isinstance(payload,dict):return None,'no gauge metadata'
    if str(payload.get('usgsId') or '').zfill(8)!=str(usgs).zfill(8):
        return None,'NOAA gauge USGS ID does not match requested site'
    reach=payload.get('reachId')
    return (str(reach),'candidate: NOAA gauge metadata') if reach else (None,'NOAA gauge has no reachId')

def run(config,output,enable_gis=False):
    pairs=json.loads(pathlib.Path(config).read_text())['pairs']
    output=pathlib.Path(output);output.mkdir(parents=True,exist_ok=True)
    audit=[];cache={};results={};reach_candidates=set()
    for name,pair in pairs.items():
        site=pair.get('usgs_site')
        item={'usgs_site':site,'gauge_candidate':None,'mouth_candidates':[],
              'gauge_review':'unavailable','mouth_review':'not surveyed',
              'gauge_verified':bool(pair.get('gauge_match_verified')),
              'mouth_verified':bool(pair.get('mouth_match_verified'))}
        if site:
            # NOAA supports USGS-prefixed identifiers; no NWM ID inference.
            url=BASE+'gauges/USGS-'+urllib.parse.quote(str(site))
            if url not in cache:cache[url]=request(url,audit)
            rid,reason=gauge_match(cache[url],site)
            item['gauge_candidate']=rid;item['gauge_review']=reason
            if rid:reach_candidates.add(rid)
        # Mouth coordinates MUST be independently surveyed. The generalized
        # dashboard coordinates are deliberately NOT used for this matching.
        coord=pair.get('verified_mouth_lonlat')
        if enable_gis and isinstance(coord,list) and len(coord)==2:
            lon,lat=map(float,coord)
            if -180<=lon<=180 and -90<=lat<=90:
                # 0.02 degree candidate window; NOT a distance or topology test.
                bbox=','.join(str(v) for v in (lon-.02,lat-.02,lon+.02,lat+.02))
                qs=urllib.parse.urlencode({'f':'json','geometry':bbox,'geometryType':'esriGeometryEnvelope',
                    'inSR':4326,'spatialRel':'esriSpatialRelIntersects','outFields':'*',
                    'returnGeometry':'true','outSR':4326,'resultRecordCount':50})
                obj=request(GIS+'?'+qs,audit,cap=2_000_000)
                if isinstance(obj,dict):
                    features=obj.get('features',[])
                    item['mouth_candidates']=[{'attributes':f.get('attributes',{}),
                        'geometry':f.get('geometry')} for f in features[:50]]
                    item['mouth_review']='GIS candidates require tributary identity, downstream topology, mouth offset and NWM version review'
                    for f in features[:50]:
                        a=f.get('attributes',{})
                        rid=a.get('feature_id') or a.get('FEATURE_ID')
                        if rid:reach_candidates.add(str(rid))
                else:item['mouth_review']='GIS unavailable; retain unverified'
        results[name]=item
    # Metadata only for small candidate set, never bulk NWM downloads.
    metadata={}
    for rid in sorted(reach_candidates)[:150]:
        obj=request(BASE+'reaches/'+urllib.parse.quote(rid,safe=''),audit)
        metadata[rid]=obj.get('reach') if isinstance(obj,dict) else None
    stamp=dt.datetime.now(dt.timezone.utc).isoformat()
    report={'generated_utc':stamp,'policy':'Candidate discovery only; NEVER auto-approve IDs',
            'nodes':results,'reach_metadata':metadata,'requests':audit}
    (output/'nwm_crosswalk_candidates.json').write_text(json.dumps(report,indent=2))
    with (output/'nwm_crosswalk_review.csv').open('w',newline='') as fh:
        writer=csv.DictWriter(fh,fieldnames=['tributary','usgs_site','gauge_candidate','gauge_review',
            'mouth_candidate_count','mouth_review','gauge_verified','mouth_verified'])
        writer.writeheader()
        for name,r in results.items():
            writer.writerow({'tributary':name,'usgs_site':r['usgs_site'],
                'gauge_candidate':r['gauge_candidate'],'gauge_review':r['gauge_review'],
                'mouth_candidate_count':len(r['mouth_candidates']),'mouth_review':r['mouth_review'],
                'gauge_verified':r['gauge_verified'],'mouth_verified':r['mouth_verified']})
    print(f'NWM crosswalk: {len(results)} tributaries; {len(reach_candidates)} unique candidate reaches; {len(audit)} requests; 0 automatic approvals')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default=str(ROOT/'config/nwm_reach_pairs.json'))
    parser.add_argument('--output',default=str(ROOT/'output'))
    parser.add_argument('--enable-gis',action='store_true',help='Query NOAA GIS only for independently verified mouth coordinates in config')
    args=parser.parse_args()
    run(args.config,args.output,args.enable_gis)
