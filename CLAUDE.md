# Keel — project state

**Read this first. Do not re-explore the repo to rediscover state.**
Deeper context only if needed: `docs/DECISIONS.md` (why) · `docs/BUILDLOG.md` (what).

---

## Thesis (do not re-derive)

Churn prediction is a commodity. The unsolved problem is **retention decisioning under
small-sample causal uncertainty**. Keel decides *who to treat, with what, at what cost*
— and **abstains** when the CATE posterior is too wide. Vertical: subscription
(contractual) first; e-commerce/BTYD is Phase 7.

**Proven (Phase 0):** churn-score targeting loses money, worse than random 6/6 seeds;
abstention beats ranking (209 > 718). **(Phase 1):** PIT features prevent a 0.35 AUC
inflation (0.603 vs 0.954).

**Real-data checks (Hillstrom, Criteo, Lenta RCTs).** Worse-than-random did NOT
replicate (D-020). **Governing quantity = corr(τ, propensity)** (D-026): Criteo +0.61 →
uplift adds 0.6%; Lenta +0.18 → 10.4%; Hillstrom +0.07 → 3.9%; churn −0.19 → **+107%**.
When orderings coincide the outcome model wins (easier estimand). Retention is the
adversarial case. Lenta was an **out-of-sample prediction and it landed** (D-031),
though underpowered to test the consequence. Small-n: uplift beats random on only
**75% of seeds at n=500** (D-023). Prior art: Ascarza, JMR 2018.

---

## Status

**Phases 0-1 COMPLETE + 3 real-RCT validations.** 172 tests. CI green.
**Next: Phase 2** — dunning / involuntary churn. The first thing that earns money.

| # | Phase | Status | Gate |
|---|---|---|---|
| 0 | SubSim + kill test | ✅ **done** | churn-score policy provably loses money |
| 1 | Canonical schema, PIT feature store, ingest | ✅ **done** | leakage suite green in CI |
| 2 | Dunning / involuntary churn + retry-timing model | ⬜ **next** | **first revenue — get a paying client** |
| 3 | Discrete-time survival hazard + CLV | ⬜ | beats Cox/RSF/DeepSurv on public data; calibrated |
| 4 | Hierarchical Bayesian CATE + abstention | ⬜ | **paper 2**; beats baselines on net revenue at small n |
| 5 | Offer-ladder optimizer + reason codes + dashboard | ⬜ | owner can act without asking us |
| 6 | Holdout infra + incrementality reports + cancel widget | ⬜ | **real client ROI number**; paper 3 |
| 7 | Cross-tenant priors, BTYD router, integrations | ⬜ | tenant #10 beats tenant #1 on day 1 |

**Papers:** merge 1+2 → small-*n* abstention + the corr(τ,propensity) principle
(fig 2, 3 = real-data support) · 3) margin-aware offer allocation.

---

## Invariants — breaking these invalidates results

1. **Temporal splits only.** Train on months < T, predict at T. Never random split.
2. **Latents never enter `panel`.** CI-enforced (`test_latents_do_not_leak_into_panel`).
   `latents` and `hidden_state` are ORACLE-ONLY.
3. **Never hand-tune the hazard intercept.** Run `calibration.calibrate_intercept`
   after changing *any* hazard coefficient or latent distribution.
4. **`mean_tau` must stay negative.** The offer must help on average, so losses are
   attributable to targeting alone. Calibration gate enforces it.
5. **Voluntary and involuntary churn stay separate processes.** Never sum them.
6. **Value is measured against `do_nothing`**, never save-rate-among-treated.
7. **Phase 0 deps = numpy/pandas/scipy only.** Heavy ML libs are `pyproject` extras.
8. Read `docs/DECISIONS.md` before changing a modelling choice — it may already be
   settled and the reasoning may be adverse to the obvious move.
9. **Every fact carries `occurred_at` AND `available_at`.** Features filter on
   `available_at`, never `occurred_at`. `FeatureStore._visible` is the only path to
   source data — never read a canonical table directly in a feature.
10. **`FeatureStore` unsafe modes are for measurement only.** Nothing in the production
    path may pass `mode=`. Default is `SAFE`; a test enforces it.

---

## Map

```
keel/core/                 schema (occurred_at+available_at) · features (_visible is the
                           ONLY path to data) · leakage (audit, time-travel, canary)
keel/ingest/               stripe (pure, fixture-tested) · csv_ingest · subsim_adapter
keel/sim/                  config · latents (copula) · hazard (ONE defn, two regimes)
                           subsim (panel) · counterfactual (exact τ, CRN, LADDER)
                           calibration (check, check_quadrants, calibrate_intercept)
keel/experiments/          kill_test · leakage_penalty · figures
keel/benchmarks/           datasets (Hillstrom, Criteo, Lenta) · models · evaluate · small_n
                           spectrum (when uplift pays) · figures
tests/                     172 tests — fairness, realism, edge cases, leakage gate
explainer/                 10 docs for non-technical evaluators/investors (see protocol)
```

## Commands

```bash
make check      # lint + 172 tests + calibration gates — run before every commit
make killtest   # re-run the founding experiment
make figures    # regenerate figures, auto-syncs explainer/figures/
make help       # everything else
```
Remote: `origin` → https://github.com/PrashamJ17/PBL-Proj (`main`). CI gates on every
push: tests (3.11-3.13) · calibration · **leakage** · **kill test**.

---

## Update protocol

Every session: **this file** — flip phase status, move **next**, add ONE checkpoint
line; add an invariant only if something must never break again.
**Detail elsewhere:** `docs/BUILDLOG.md` (what happened + tested) · `docs/DECISIONS.md`
(why — append D-0NN, never edit past entries).

**On phase completion — `explainer/`** (non-technical: evaluators + investors):
always update `09-status-and-roadmap.md` (flip row + append change-log). Update others
only if the phase changed what they claim: `05` new results (incl. honest-status),
`04` architecture, `06` pricing/competitors, `07` risks, `08` new terms.
*Rules:* zero assumed knowledge, define every term, **never claim more than was
demonstrated** — those readers cannot check us.

**Then commit and push — every checkpoint, no exceptions:**
```bash
make check && git add -A && git commit && git push origin main
```
Message leads with what it **establishes or fixes**, not files touched; moved numbers
in the body; cite `D-0NN`. Phase completion → `CHANGELOG.md` entry first (newest
first). Never commit on red — if blocked, commit *with the failure described* rather
than leaving work uncommitted.

Keep this file under ~120 lines. If it grows, cut history, not invariants.

---

## Checkpoints

- **CP-01** — Phase 0 complete. SubSim calibrated, kill test 6/6 seeds, figure 1.
- **CP-02** — Phase 1 complete. Canonical schema, PIT store, leakage suite, ingest.
- **CP-03** — Hillstrom: worse-than-random did NOT replicate → claim scoped (D-020).
  Small-n unreliability found (75% win rate at n=500) → D-023, figure 2.
- **CP-04** — Criteo added. Uplift LOSES to outcome models there; reconciled by
  corr(τ,propensity) as the governing quantity (D-026, figure 3). Criteo file is
  treatment-sorted — prefix reads invalid (D-024).
- **CP-05** — Lenta added as an OUT-OF-SAMPLE test of D-026: predicted to land between
  advertising and churn, landed at +0.18 (D-031). Underpowered to test the consequence
  (ATE only +7.4% lift). Two CI failures fixed — unpinned ruff rule set (D-028) and a
  pandas-resolution assertion (D-030). 172 tests, CI green.
  Next: Phase 2 dunning — first revenue.
