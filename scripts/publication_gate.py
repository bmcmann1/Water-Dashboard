#!/usr/bin/env python3
"""Fail closed on empty/malformed acquisition; never require every station fresh."""
import pathlib,json,sys
p=pathlib.Path('output/normalized_network.json');s=pathlib.Path('site/index.html')
if not p.is_file() or not s.is_file():sys.exit('Missing normalized network or dashboard')
d=json.loads(p.read_text());nodes=d.get('nodes',{})
if len(nodes)!=42:sys.exit('Expected 42 nodes, got '+str(len(nodes)))
# Do not publish a fully empty acquisition, even if a baseline/previous HTML exists.
noaa=sum(bool(n.get('noaa',{}).get('observed_stage') or n.get('noaa',{}).get('observed_flow')) for n in nodes.values())
if noaa<10:sys.exit('Publication blocked: fewer than 10 NOAA stations with observed stage/flow ('+str(noaa)+')')
if s.stat().st_size<10000:sys.exit('Dashboard unexpectedly small')
print('Publication gate passed; NOAA observation stations:',noaa,'nodes:',len(nodes))
