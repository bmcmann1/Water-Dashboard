#!/usr/bin/env python3
"""Acquire and parse Wilbur D. Mills Dam total release from the published SWL table."""
import datetime as dt,hashlib,json,pathlib,re,urllib.request
from html import unescape
from zoneinfo import ZoneInfo
P=pathlib.Path('output');P.mkdir(exist_ok=True);url='https://www.swl-wc.usace.army.mil/pages/data/tabular/htm/d02.htm'
audit={'source':url,'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'http_status':None,'records':0,'error':None,'series':[]}
try:
 req=urllib.request.Request(url,headers={'User-Agent':'MississippiHydraulicNetwork/16'})
 with urllib.request.urlopen(req,timeout=22) as r:raw=r.read(2_000_001);audit['http_status']=r.status
 if len(raw)>2_000_000:raise ValueError('2 MB limit exceeded')
 audit['bytes']=len(raw);audit['sha256']=hashlib.sha256(raw).hexdigest()
 path=P/'raw/priority/mills';path.mkdir(parents=True,exist_ok=True);(path/'source.html').write_bytes(raw)
 plain=unescape(re.sub(r'<[^>]+>',' ',raw.decode('utf-8','replace')));plain=re.sub(r'\s+',' ',plain)
 # date, time, pool, tailwater, turbine, spillway, total. Missing rows are ignored.
 pat=re.compile(r'(\d{2}[A-Z]{3}\d{4})\s+(\d{4})\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)')
 for d,hhmm,pool,tail,turb,spill,total in pat.findall(plain):
  try:
   base=dt.datetime.strptime(d,'%d%b%Y');hh=int(hhmm[:2]);mm=int(hhmm[2:])
   if hh==24:base+=dt.timedelta(days=1);hh=0
   t=base.replace(hour=hh,minute=mm,tzinfo=ZoneInfo('America/Chicago')).astimezone(dt.timezone.utc)
   audit['series'].append({'time':t.isoformat(),'pool_ft':float(pool),'tailwater_ft':float(tail),'turbine_release_cfs':float(turb.replace(',','')),'spillway_release_cfs':float(spill.replace(',','')),'total_release_cfs':float(total.replace(',',''))})
  except Exception:pass
 audit['records']=len(audit['series']);audit['table_present']='Total' in plain and 'Release' in plain
 audit['status']='PARSED_TOTAL_RELEASE' if audit['records'] else ('UNRECOGNIZED_TABLE' if not audit['table_present'] else 'TABLE_PRESENT_NO_VALID_ROWS')
except Exception as e:audit['error']=repr(e);audit['status']='ACQUISITION_FAILED'
(P/'mills_dam_acquisition.json').write_text(json.dumps(audit,indent=2));print('Mills dam:',audit['status'],'rows:',audit['records'])
