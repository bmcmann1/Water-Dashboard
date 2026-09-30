# v12 installation — publication-test isolation and conditional backups

Upload the files in this patch to their matching GitHub paths. Replace the existing versions.

- `scripts/publication_gate.py`: optional explicit audit paths for isolated tests; production consistency enforcement unchanged.
- `tests/test_publication_gate.py`: NOAA fixture tests explicitly disable unrelated on-disk reports.
- `scripts/discover_fallbacks.py`: fresh primary discharge skips redundant optional nearby-catalog calls; gaps still trigger discovery and actionable alternatives.
- `scripts/verify_release.py`: optional backup discovery is not a release requirement for nodes with valid primary discharge.
- `.github/workflows/mississippi-combined-dashboard.yml`: normalization precedes conditional discovery; catalog outages do not stop the build.
- `tests/test_fallback_discovery.py`: tests fresh-primary and stale-primary cases.

Run **Mississippi Combined Dashboard — Manual First**. All original primary acquisition, hydraulic QC and production publication safeguards remain enabled. The patch does not claim that a measured upstream gauge establishes mouth equivalence.
