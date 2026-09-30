# v11 — full-workflow deployment attempt

**Upload the contents of this ZIP to your GitHub repository root**, preserving directories. This is a **cumulative repository ZIP**, not an incremental standalone map. Upload only changed/new files if using the GitHub web interface; see `V11_CHANGED_FILES.md`.

Run Actions → Mississippi Combined Dashboard — Manual First → Run workflow. Download `mississippi-combined-audit-*` and `github-pages` artifacts after completion.

The workflow runs NOAA and HEFS, three-route USGS, bounded CWMS discovery, verified NWM, approved USACE series, NWM pairing, all-source verification, *targeted USGS site-catalog discovery for missing discharge and operations*, normalization, continuity, map building, release tests and publication gate. It writes `output/fallback_discovery.json` and embeds bounded suggestions in the HTML. Discovery never automatically treats nearby stations as mouth-equivalent.

**Critical distinction:** A successful deployment verifies software gates and minimum fresh NOAA coverage, not certification of every river reach. Unverified hydraulic substitutions remain explicitly marked and accompanied by actionable alternatives. To require all blockers resolved, set `REQUIRE_COMPLETE_HYDRAULIC_CERTIFICATION=1` on the publication gate; in that mode the run will archive diagnostics and refuse deployment when source evidence is genuinely missing.

**Efficiency:** Existing responses are reused; discovery targets only unresolved discharge/near-mouth/structure nodes, one bounded site-catalog request per georeferenced node (max 46), at most eight ranked suggestions per node, 1.5 MB response cap, no bulk timeseries downloads from unapproved candidate gauges. Requests/bytes/errors are logged. Generalized map coordinates are only search centers, not hydraulic equivalence evidence.

**Known limits:** Live APIs are accessed in GitHub Actions, not validated in this offline patch build. Some CWMS and NOAA routes may expose the same underlying sensor, and unavailable observations cannot be fabricated. Review the resulting audit before claiming full hydraulic certification.
