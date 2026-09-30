# V16 full-code manifest

This ZIP is intended as a full repository replacement.

Major v16 changes:
- `scripts/reconcile_priority_tributaries.py` — new White, St. Francis, Meramec, and Arkansas reconciliation engine.
- `scripts/acquire_priority_tributaries.py` — adds bounded NOAA checkpoint NWM acquisition and parses White River at Clarendon flow.
- `scripts/acquire_mills_dam.py` — validates and parses Wilbur D. Mills total-release rows.
- `scripts/acquire_usgs_usace.py` — automatically acquires priority-policy USGS flow/stage sites.
- `scripts/normalize_qc.py` — includes priority-policy USGS sites in normalization.
- `scripts/run_tests_report.py` — runs unittest suite and creates plain-language test report JSON.
- `scripts/build_dashboard.py` — embeds reconciliation provenance and current-run test report; applies tributary approvals before continuity solve.
- `scripts/dashboard_template.html` — adds collapsible Automated tests panel plus reconciliation status/provenance.
- `config/priority_tributary_policy.json` — v16 source/method policy.
- `tests/test_v16_reconciliation.py` — seven reconciliation guardrail tests.
- `.github/workflows/mississippi-combined-dashboard.yml` — reconciliation + test-report + rebuild workflow.
- `.github/workflows/mississippi-full-acquisition.yml` — same priority acquisition/reconciliation/test-report sequence.

Local validation performed before packaging:
- 60 unittest cases passed against the run-11 audit fixture, 0 failures/errors, 0 skips when outputs were present.
- Python compilation passed for scripts and tests.
- Embedded dashboard JavaScript passed `node --check`.

A new live acquisition was not run in this container; the next GitHub Actions run will determine current White/St. Francis/Meramec/Arkansas reconciliation status from live source data.
