# Mississippi River Hydraulic Network Dashboard — v16

Self-contained Mississippi River hydraulic-network dashboard with NOAA NWPS/HEFS, USGS, USACE, NWM guidance, acquisition diagnostics, conservative continuity, priority-tributary reconciliation, and embedded test reporting.

## Primary workflow

Run `.github/workflows/mississippi-combined-dashboard.yml` manually. It acquires data, normalizes/QCs it, reconciles priority tributaries, builds the dashboard, runs the automated tests, rebuilds the dashboard with the test report embedded, applies the publication gate, archives the audit, and deploys GitHub Pages.

## V16 priority tributary rules

- Ohio: Olmsted USGS discharge.
- Arkansas: Wilbur D. Mills total release.
- Illinois: Valley City USGS discharge.
- White: Clarendon observed flow reconciled with Norrell/St. Charles stage and lower-river NWM guidance.
- St. Francis: Helena-to-Mhoon Mississippi mainstem net-lateral residual, explicitly labeled inferred/model-assisted when applicable.
- Meramec: Eureka observed flow reconciled against Arnold/Herculaneum stage behavior and a same-model St. Louis-to-Herculaneum NWM residual.

The dashboard's **Automated tests** dropdown lists every current test in plain language and shows the result from the same workflow run. V16 contains 60 tests: the prior 53 plus 7 new reconciliation tests.

See `V16_INSTALL.md` for details.
