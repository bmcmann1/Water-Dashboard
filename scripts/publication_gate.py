#!/usr/bin/env python3
"""Publication safety gate against the actual normalized-network schema.

Count fresh, timestamped NOAA *observations*; forecasts never satisfy the gate.
An individual missing/stale station does not block a healthy network snapshot.
"""
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path('.')
NETWORK = ROOT / 'output/normalized_network.json'
QC = ROOT / 'output/qc_report.json'
DASHBOARD = ROOT / 'site/index.html'
MIN_FRESH_NOAA = 10
MAX_AGE = dt.timedelta(hours=24)


def valid_time(value):
    try:
        result = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def evaluate(network, qc, dashboard_bytes, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    nodes = network.get('nodes', {})
    if len(nodes) != 42 or qc.get('node_count') != 42:
        raise ValueError(f'Expected 42 nodes; network={len(nodes)} QC={qc.get("node_count")}')
    if dashboard_bytes < 10000:
        raise ValueError('Dashboard missing or unexpectedly small')
    fresh = []
    for node_id, node in nodes.items():
        observed = node.get('noaa', {}).get('observed', [])
        if not isinstance(observed, list):
            continue
        for point in observed:
            when = valid_time(point.get('time')) if isinstance(point, dict) else None
            value = point.get('value') if isinstance(point, dict) else None
            if when is None or not isinstance(value, (int, float)):
                continue
            age = now - when
            if dt.timedelta(0) <= age <= MAX_AGE:
                fresh.append(node_id)
                break
    if len(fresh) < MIN_FRESH_NOAA:
        raise ValueError(f'Only {len(fresh)} fresh NOAA observation stations; require {MIN_FRESH_NOAA}')
    return fresh


def main():
    for p in (NETWORK, QC, DASHBOARD):
        if not p.is_file():
            sys.exit(f'Publication blocked: missing {p}')
    try:
        fresh = evaluate(json.loads(NETWORK.read_text()), json.loads(QC.read_text()), DASHBOARD.stat().st_size)
    except (ValueError, json.JSONDecodeError) as exc:
        sys.exit('Publication blocked: ' + str(exc))
    print(f'Publication gate passed: {len(fresh)} fresh NOAA observation stations; 42 nodes; {DASHBOARD.stat().st_size:,} dashboard bytes')


if __name__ == '__main__':
    main()
