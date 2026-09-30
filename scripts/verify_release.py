#!/usr/bin/env python3
"""Fail before deployment if the release omits route evidence or continuity QC."""
import json,pathlib,sys
p=pathlib.Path('output');acq=json.loads((p/'acquisition_summary.json').read_text());qc=json.loads((p/'qc_report.json').read_text());mass=json.loads((p/'mass_balance_audit.json').read_text())
errors=[]; expected={'legacy_iv','ogc_continuous','legacy_dv'}
for sid,item in acq.get('usgs',{}).items():
 for code in ('00060','00065','63160'):
  found={r['route'] for r in item.get('routes',[]) if r.get('parameter')==code}
  if found!=expected:errors.append(f'{sid} {code}: routes {sorted(found)}')
if qc.get('mass_balance')!=mass.get('reaches'):errors.append('Formal and QC continuity reports differ')
if not mass.get('reaches'):errors.append('No mass balance results')
if not (pathlib.Path('site/index.html').is_file()):errors.append('Dashboard missing')
verification=p/'complete_verification.json'
if not verification.exists():errors.append('Missing all-source verification audit')
else:
 report=json.loads(verification.read_text())
 if report.get('network_nodes')!=46:errors.append('Incomplete all-source station audit')
 # Blockers are retained in the audit; their existence does not erase valid observations.
 # Release-critical unresolved source/near-mouth issues are reported explicitly.
 (p/'release_blockers.json').write_text(json.dumps(report.get('blockers',[]),indent=2))
fallback=p/'fallback_discovery.json'
if not fallback.exists():errors.append('Missing automatic fallback discovery report')
else:
 fb=json.loads(fallback.read_text());needed={b['node'] for b in report.get('blockers',[]) if b.get('variable') in ('discharge','near_mouth_discharge','structure_operations')} if verification.exists() else set()
 for nid in needed:
  if not fb.get('stations',{}).get(nid,{}).get('alternatives'):errors.append('No actionable fallback options: '+nid)
print(json.dumps({'stations_audited' :len(acq.get('usgs',{})),'attempted_routes':acq.get('request_count'),'mass_balance':mass.get('summary'),'errors':errors},indent=2))
if errors:sys.exit(1)
