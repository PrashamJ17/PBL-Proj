# Keel — project state

**Read this first. Do not re-explore the repo to rediscover state.**
Everything needed to resume work is here. Deeper context only if the task requires it:
`docs/DECISIONS.md` (why choices were made) · `docs/BUILDLOG.md` (what happened).

---

## Thesis (do not re-derive)

Churn prediction is a commodity. The unsolved problem is **retention decisioning under
small-sample causal uncertainty**. Keel decides *who to treat, with what, at what cost*
— and **abstains** when the CATE posterior is too wide. Vertical: subscription
(contractual) first; e-commerce/BTYD is Phase 7.

**Proven (Phase 0, 6/6 seeds):** churn-score targeting loses money and is *worse than
random*. Abstention beats ranking (209 treated > 718 treated). Sleeping dogs = 48% of
top risk decile vs 2% of bottom.

**Proven (Phase 1):** point-in-time features prevent a **0.35 AUC inflation**
(correct 0.603 · occurred-only 0.613 · unfiltered 0.954).

---

## Status

**Phases 0-1 COMPLETE.** 137 tests passing. All three CI gates green.
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

**Papers:** 1) SubSim benchmark ⬜ draftable now · 2) small-*n* uplift w/ abstention ⬜
· 3) margin-aware offer allocation ⬜

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
keel/core/schema.py        canonical tables; occurred_at + available_at on every fact
keel/core/features.py      PIT feature store; _visible() is the ONLY path to data
keel/core/leakage.py       availability audit, time-travel, canary injection
keel/ingest/               stripe.py (pure, fixture-tested) · csv_ingest.py · subsim_adapter.py
keel/sim/                  config · latents (copula) · hazard (ONE defn, two regimes)
                           subsim (panel) · counterfactual (exact τ, CRN, LADDER)
                           calibration (check, check_quadrants, calibrate_intercept)
keel/experiments/          kill_test · leakage_penalty · figures
tests/                     137 tests — fairness, realism, edge cases, leakage gate
explainer/                 10 docs for non-technical evaluators/investors (see protocol)
```

## Commands

```bash
make check      # lint + 137 tests + calibration gates — run before every commit
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

- **CP-01** — Phase 0 complete. SubSim calibrated (4.5% monthly voluntary churn, 30%
  involuntary share, 17% sleeping dogs, mean τ=−0.010), kill test passed 6/6 seeds,
  figure 1 generated, 58 tests green.
- **CP-02** — Phase 1 complete. Canonical schema, PIT feature store, leakage suite,
  Stripe/CSV/SubSim ingest. Leakage penalty measured: 0.603 correct vs 0.954
  unfiltered. 137 tests green, 4 CI gates. Next: Phase 2 dunning — first revenue.
