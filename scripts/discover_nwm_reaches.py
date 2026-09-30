#!/usr/bin/env python3
"""Bounded NWM crosswalk discovery; produces candidates, NEVER approvals.

STEP 1. Load all 20 tributaries and the already-acquired USGS station records.
STEP 2. Recover USGS coordinates from raw observations (zero extra requests).
STEP 3. Query NOAA NWM GIS in small windows around gauges and approximate
        junctions. Junction coordinates are DISPLAY-ONLY and cannot approve IDs.
STEP 4. Deduplicate candidate reach IDs and request metadata only once.
STEP 5. Save full HTTP diagnostics and a concise human-review CSV.

Costs: no national hydrofabric downloads; <= 2 spatial queries per tributary,
<= 100 distinct metadata queries; one bounded retry for transient failures.
"""
import argparse,csv,datetime as dt,json,pathlib,time,urllib.error,urllib.parse,urllib.request
ROOT=pathlib.Path(__file__).resolve().parent.parent
BASE='https://api.water.noaa.gov/nwps/v1/'
GIS='https://mapservices.weather.noaa.gov/vector/rest/services/obs/NWM_Stream_Analysis/MapServer/5/query'
HEAD={'User-Agent':'Mississippi-Hydraulic-Network/4.0 (crosswalk review)','Accept':'application/json'}
# Station IDs already selected by the existing USGS acquisition workflow.
# These are candidates, not proof of current discharge or nearest-mouth coverage.
REFERENCE={'illinois':'05587060','missouri':'06935965','meramec':'07019130',
 'kaskaskia':'05595000','bigmuddy':'05599500','hatchie':'07029500',
 'loosahatchie':'07030357','wolf':'07031740','white':'07077830',
 'arkansas':'07265280','yazoo':'07288800','bigblack':'07290000',
 'homochitto':'07292500','bayousara':'07373300','cuivre':'05514500',
 'obion':'07026040'}

def request(url,log,cap=1_500_000):
    row={'url':url,'http_status':None,'retrieved_utc':None,'error':None}
    for attempt in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=HEAD),timeout=22) as r:
                row['http_status']=r.status;data=r.read(cap+1)
            if len(data)>cap:raise ValueError('response over bounded size')
            obj=json.loads(data)
            if isinstance(obj,dict) and obj.get('error'):raise ValueError('service error: '+str(obj['error'])[:350])
            row['retrieved_utc']=dt.datetime.now(dt.timezone.utc).isoformat();log.append(row)
            return obj
        except urllib.error.HTTPError as e:
            row['http_status']=e.code;row['error']=str(e)
            if e.code not in (429,500,502,503,504):break
        except (urllib.error.URLError,TimeoutError,ValueError) as e:row['error']=str(e)
        if attempt==0:time.sleep(1)
    log.append(row);return None

def existing_usgs_metadata(site,raw_dir):
    """Use data already downloaded by the main workflow; no duplicate USGS call."""
    for param in ('00060','00065','63160'):
        path=raw_dir/str(site)/(param+'_legacy.json')
        if not path.exists():continue
        try:
            obj=json.loads(path.read_text())
            for ts in obj.get('value',{}).get('timeSeries',[]):
                info=ts.get('sourceInfo',{})
                if str(info.get('siteCode',[{}])[0].get('value','')).zfill(8)!=str(site).zfill(8):continue
                geo=info.get('geoLocation',{}).get('geogLocation',{})
                lon,lat=geo.get('longitude'),geo.get('latitude')
                if lon is not None and lat is not None:return {'lon':float(lon),'lat':float(lat),'name':info.get('siteName'),'source':str(path)}
        except (OSError,ValueError,IndexError,TypeError):continue
    return None

def spatial_query(lon,lat,log,half_width=.025):
    """Small candidate window. Nearness does NOT prove river identity or routing."""
    bbox=','.join(map(str,(lon-half_width,lat-half_width,lon+half_width,lat+half_width)))
    q=urllib.parse.urlencode({'f':'json','geometry':bbox,'geometryType':'esriGeometryEnvelope',
        'inSR':4326,'spatialRel':'esriSpatialRelIntersects','outFields':'*',
        'returnGeometry':'true','outSR':4326,'resultRecordCount':35})
    data=request(GIS+'?'+q,log,cap=2_000_000)
    if not isinstance(data,dict):return [],'GIS request failed; inspect HTTP log'
    features=data.get('features',[])
    if not isinstance(features,list):return [],'GIS response has no feature list'
    out=[]
    for f in features[:35]:
        a=f.get('attributes',{});rid=a.get('feature_id') or a.get('FEATURE_ID') or a.get('featureId')
        out.append({'reach_id':str(rid) if rid is not None else None,'attributes':a,'geometry':f.get('geometry')})
    return out,('Candidate search succeeded' if out else 'No reaches in search window')

def run(config,output,enable_gis=False,raw_dir=None,geography=None):
    cfg=json.loads(pathlib.Path(config).read_text())['pairs'];out=pathlib.Path(output);out.mkdir(parents=True,exist_ok=True)
    raw_dir=pathlib.Path(raw_dir or ROOT/'output/raw/usgs')
    geography=pathlib.Path(geography or ROOT/'config/geography.json')
    approx=json.loads(geography.read_text()).get('positions',{}) if geography.exists() else {}
    audit=[];cache={};results={};ids=set()
    for name,p in cfg.items():
        site=p.get('usgs_site') or REFERENCE.get(name)
        item={'usgs_site':site,'gauge_metadata':None,'gauge_candidates':[],
            'gauge_review':'No USGS reference station','mouth_candidates':[],
            'mouth_review':'No approximate junction coordinates',
            'mouth_coordinate_status':'unavailable',
            'gauge_verified':bool(p.get('gauge_match_verified')),
            'mouth_verified':bool(p.get('mouth_match_verified'))}
        if site:
            meta=existing_usgs_metadata(site,raw_dir);item['gauge_metadata']=meta
            if meta and enable_gis:
                key=('gauge',site)
                if key not in cache:cache[key]=spatial_query(meta['lon'],meta['lat'],audit)
                item['gauge_candidates'],item['gauge_review']=cache[key]
            else:item['gauge_review']='No reusable USGS coordinates' if not meta else 'GIS disabled'
        # Prefer explicitly surveyed mouth coordinates. Generalized positions are
        # allowed only for candidate discovery, never for geographic approval.
        coord=p.get('verified_mouth_lonlat');verified=isinstance(coord,list) and len(coord)==2
        if not verified:coord=approx.get(name)
        if isinstance(coord,list) and len(coord)==2:
            item['mouth_coordinate_status']='verified input' if verified else 'approximate map location: discovery ONLY'
            if enable_gis:
                try:item['mouth_candidates'],item['mouth_review']=spatial_query(float(coord[0]),float(coord[1]),audit,half_width=.035)
                except (ValueError,TypeError):item['mouth_review']='Invalid junction coordinates'
            else:item['mouth_review']='GIS disabled'
        for f in item['gauge_candidates']+item['mouth_candidates']:
            if f['reach_id']:ids.add(f['reach_id'])
        results[name]=item
    # Metadata fetch is deduplicated and capped, including across gauge and mouth.
    metadata={}
    for rid in sorted(ids)[:100]:
        metadata[rid]=request(BASE+'reaches/'+urllib.parse.quote(rid,safe=''),audit)
    report={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'policy':'Candidate discovery only; GIS proximity and map coordinates never auto-approve IDs',
        'nodes':results,'reach_metadata':metadata,'requests':audit,
        'metadata_cap_hit':len(ids)>100}
    (out/'nwm_crosswalk_candidates.json').write_text(json.dumps(report,indent=2))
    with (out/'nwm_crosswalk_review.csv').open('w',newline='') as fh:
        cols=['tributary','usgs_site','gauge_coordinate_source','gauge_candidate_count',
            'gauge_review','mouth_coordinate_status','mouth_candidate_count','mouth_review',
            'gauge_verified','mouth_verified']
        w=csv.DictWriter(fh,fieldnames=cols);w.writeheader()
        for name,r in results.items():w.writerow({'tributary':name,'usgs_site':r['usgs_site'],
            'gauge_coordinate_source':(r['gauge_metadata'] or {}).get('source',''),
            'gauge_candidate_count':len(r['gauge_candidates']),'gauge_review':r['gauge_review'],
            'mouth_coordinate_status':r['mouth_coordinate_status'],
            'mouth_candidate_count':len(r['mouth_candidates']),'mouth_review':r['mouth_review'],
            'gauge_verified':r['gauge_verified'],'mouth_verified':r['mouth_verified']})
    print(f'NWM crosswalk: {len(results)} tributaries; {len(ids)} unique GIS candidates; {len(audit)} HTTP requests; zero automatic approvals')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',default=str(ROOT/'config/nwm_reach_pairs.json'))
    p.add_argument('--output',default=str(ROOT/'output'))
    p.add_argument('--enable-gis',action='store_true')
    args=p.parse_args();run(args.config,args.output,args.enable_gis)
