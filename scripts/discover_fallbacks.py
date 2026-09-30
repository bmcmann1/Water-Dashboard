#!/usr/bin/env python3
"""Bounded, read-only fallback discovery after primary acquisition; never auto-approve proximity.

Uses already collected verification to target missing nodes. NOAA metadata USGS IDs
and a small USGS site-catalog bounding box are *candidate discovery*, not proof
of hydraulic equivalence. Reuse existing raw responses and never re-fetch a site.
"""
import datetime as dt
import json, math, pathlib, urllib.parse, urllib.request, urllib.error, hashlib, time, csv, io
ROOT=pathlib.Path("output")
REG=json.loads(pathlib.Path("network_registry.json").read_text())
GEO=json.loads(pathlib.Path("config/geography.json").read_text())["positions"]
MAX_NODES=46; MAX_CANDIDATES=8; MAX_BYTES=1_500_000
HEAD={"User-Agent":"Mississippi-Hydraulic-Dashboard/11 (bounded research)","Accept":"text/plain,application/json"}
def load(path,default=None):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def distance_km(a,b):
    lon1,lat1=a;lon2,lat2=b;r=6371.0
    p1,p2=math.radians(lat1),math.radians(lat2)
    h=math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 2*r*math.asin(min(1,math.sqrt(h)))

def parse_rdb(payload):
    lines=[x for x in payload.splitlines() if x and not x.startswith("#")]
    if len(lines)<3:return []
    rows=[]
    for row in csv.DictReader(io.StringIO("\n".join([lines[0]]+lines[2:])),delimiter="\t"):
        try:
            sid=row.get("site_no","").strip();lon=float(row["dec_long_va"]);lat=float(row["dec_lat_va"])
            if sid.isdigit() and 7<=len(sid)<=15:rows.append({"site":sid,"name":row.get("station_nm",""),"lon":lon,"lat":lat})
        except (KeyError,ValueError,TypeError):continue
    return rows

def discover(node,position,existing_sites,fetch=None):
    """Return ranked *unapproved* nearby candidates; catalog proximity is not routing evidence."""
    lon,lat=position;delta=0.42
    bbox=f"{lon-delta:.4f},{lat-delta:.4f},{lon+delta:.4f},{lat+delta:.4f}"
    query={"format":"rdb","bBox":bbox,"siteType":"ST","siteStatus":"active","siteOutput":"expanded","parameterCd":"00060"}
    url="https://waterservices.usgs.gov/nwis/site/?"+urllib.parse.urlencode(query)
    attempt={"route":"USGS_site_catalog_nearby","url":url,"retrieved_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"status":None,"bytes":0,"error":None}
    try:
        if fetch is None:
            with urllib.request.urlopen(urllib.request.Request(url,headers=HEAD),timeout=18) as response:
                data=response.read(MAX_BYTES+1);attempt["status"]=response.status
        else:data=fetch(url);attempt["status"]=200
        if len(data)>MAX_BYTES:raise ValueError("Catalog exceeds 1.5 MB safety cap")
        attempt["bytes"]=len(data);attempt["sha256"]=hashlib.sha256(data).hexdigest()
        candidates=[]
        for row in parse_rdb(data.decode("utf-8",errors="replace")):
            if row["site"] in existing_sites:continue
            km=distance_km(position,(row["lon"],row["lat"]))
            candidates.append({**row,"distance_km":round(km,1),"approval":"NOT_APPROVED","reason":"Nearby site; confirm river, drainage area, intervening inflows, backwater and travel time"})
        candidates.sort(key=lambda r:r["distance_km"])
        return candidates[:MAX_CANDIDATES],attempt
    except (urllib.error.URLError,TimeoutError,ValueError,OSError) as exc:
        attempt["error"]=str(exc);return [],attempt

def has_primary_discharge(node, normalized, now=None):
    """Require a fresh measured discharge; stage/forecast/model guidance is not a substitute.

    This is a discovery-priority check, not an approval of tributary mouth equivalence.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    obj = normalized.get('nodes', {}).get(node, {})
    streams = [v.get('00060', []) for v in obj.get('usgs', {}).values()]
    streams += [obj.get('usace', {}).get('discharge', [])]
    for series in streams:
        for point in series:
            try:
                when = dt.datetime.fromisoformat(point['time'].replace('Z', '+00:00'))
                value = float(point['value'])
                unit = str(point.get('unit', '')).lower().replace(' ', '')
                if (when.tzinfo and math.isfinite(value) and value >= 0
                    and unit in ('cfs','ft3/s','ft^3/s','ft³/s','cms','m3/s','m³/s')
                    and -2 <= (now - when).total_seconds()/3600 <= 24):
                    return True
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
    return False


def plan(root=ROOT,fetch=None):
    verification=load(root/"complete_verification.json",{})
    acq=load(root/"acquisition_summary.json",{})
    nodes={n["id"]:n for n in REG["reaches"]+REG["junctions"]}
    known=set(acq.get("usgs",{}))
    target={b["node"] for b in verification.get("blockers",[]) if b.get("variable") in ("discharge","near_mouth_discharge","structure_operations")}
    normalized=load(root/'normalized_network.json',{})
    results={};attempts=[];primary_available=[];failures=[]
    for nid in sorted(target)[:MAX_NODES]:
        node=nodes.get(nid,{});station=verification.get("stations",{}).get(nid,{})
        options=[]
        # Existing fresh primary data satisfies routine observation acquisition.
        # Retain cheap cached cross-references; do not make optional catalog HTTP
        # traffic a requirement or spend bandwidth on already-covered nodes.
        primary=has_primary_discharge(nid, normalized)
        if primary:primary_available.append(nid)
        # Reuse NOAA's returned metadata; a cross-referenced ID is stronger than proximity.
        lid=node.get("lid");meta=load(root/"raw/nwps"/str(lid)/"metadata.json",{}) if lid else {}
        for key in ("usgsId","usgs_id","usgsSiteId"):
            sid=str(meta.get(key) or "").replace("USGS-","") if isinstance(meta,dict) else ""
            if sid.isdigit() and sid not in known:
                options.append({"route":"NOAA_metadata_USGS_cross_reference","site":sid,"approval":"NOT_APPROVED","reason":"Confirm returned metadata refers to correct gauge and discharge variable"})
        if nid in GEO and not primary:
            nearby,attempt=discover(nid,GEO[nid],known,fetch)
            attempts.append({"node":nid,**attempt})
            if attempt.get('error'):failures.append({'node':nid,'error':attempt['error'],'optional':False})
            options.extend({"route":"USGS_nearby_catalog",**c} for c in nearby)
        # Existing NWM candidates are evaluated by existing pairing verifier, not inferred from location.
        pair=load(root/"nwm_pairing_verification.json",{}).get("nodes",{}).get(nid,{})
        if pair and not pair.get("mouth_approved"):
            options.append({"route":"NWM_pairing_review","approval":"NOT_APPROVED","reason":"Review reach topology, near-mouth position, upstream area and modeled/observed timing","pairing_evidence":pair})
        if nid in ("oldriver","morganza","bonnet","davis","caernarvon"):
            options.append({"route":"USACE_operations_catalog_review","approval":"NOT_APPROVED","reason":"Inspect existing bounded CWMS discovery for exact approved operations series"})
        if not options and not primary:options.append({"route":"hydraulic_reconstruction_review","approval":"NOT_APPROVED","reason":"Evaluate adjacent verified mainstem gauges, routing/travel time, tributary contributions and storage; no automatic substitution"})
        results[nid]={"name":node.get("name",nid),"primary_discharge_available":primary,
                      "fallback_required":not primary,"alternatives":options,
                      "next_action":"Primary observation available; optional backup discovery deferred" if primary else "Verify hydrologic connectivity and time compatibility; acquire candidate only after review"}
    out={"generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"targeted_nodes":len(results),"stations":results,"catalog_attempts":attempts,"primary_available_nodes":primary_available,"catalog_failures":failures,"policy":"All suggestions are unapproved; none are silently added to continuity calculations.","bytes_transferred":sum(a.get("bytes",0) for a in attempts)}
    root.mkdir(exist_ok=True);(root/"fallback_discovery.json").write_text(json.dumps(out,indent=2))
    print(json.dumps({"targeted_nodes":len(results),"catalog_requests":len(attempts),"bytes":out["bytes_transferred"]}))
    return out
if __name__=="__main__":plan()
