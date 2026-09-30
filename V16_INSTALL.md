# V16 — Full replacement

Install this as a full repository replacement while preserving `.github/`, `config/`, `scripts/`, and `tests/`.

Run **Mississippi Combined Dashboard — Manual First** from GitHub Actions.

## What v16 adds

1. **White River reconciliation**
   - USACE Clarendon (NPTA4) observed flow is the quantitative anchor when fresh.
   - NOAA Norrell (NOGA4) and St. Charles (SCHA4) stage changes are lower-river/backwater diagnostics only.
   - NWM analysis at lower-river checkpoints is an independent modeled comparison; stage is never converted to discharge.

2. **St. Francis-area reconciliation**
   - Uses a bounding Mississippi residual between Helena (HEEA4) and Tunica Mhoon Landing (MHOM6).
   - Uses observed flow only if the NOAA payload explicitly validates flow units; otherwise uses same-model NWM analysis at both checkpoints.
   - The value is labeled a **St. Francis-area net lateral residual**, not an isolated measured St. Francis discharge.
   - Non-positive residuals are not promoted as tributary flow.

3. **Meramec reconciliation**
   - Eureka USGS 07019000 remains the primary observed flow.
   - Arnold and Herculaneum stage changes diagnose lower-river/backwater behavior.
   - Same-model NWM flow at St. Louis (EADM7) and Herculaneum (HRCM7) provides a mainstem residual cross-check and a clearly labeled model fallback only if Eureka is unavailable.

4. **Arkansas River completion**
   - Parses the published Wilbur D. Mills Dam turbine, spillway and total-release rows with America/Chicago timestamps.
   - Fresh total release is eligible as the downstream controlled-flow estimate.

5. **Automated-test dropdown**
   - The old suite had 53 tests.
   - V16 adds 7 reconciliation tests, so the dashboard now reports **60 tests**.
   - GitHub Actions performs a pre-test dashboard build, runs `scripts/run_tests_report.py`, writes `output/test_results.json`, and rebuilds the dashboard so every test is listed in plain language with PASS / FAIL / ERROR / SKIP status.

## Important provenance rule

Stage-only observations are never converted to discharge. Model-assisted residuals remain labeled modeled/inferred. Reconciled tributary values enter continuity only when the reconciliation product marks them usable for that run.
