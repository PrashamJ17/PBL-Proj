# Keel — project state

**Read this first. Do not re-explore the repo to rediscover state.**
Deeper context only if needed: `docs/DECISIONS.md` (why) · `docs/BUILDLOG.md` (what).

---

## Thesis (do not re-derive)

Churn prediction is a commodity. The unsolved problem is **retention decisioning under
small-sample causal uncertainty**. Keel decides *who to treat, with what, at what cost*
— and **abstains** when the CATE posterior is too wide. Vertical: subscription
(contractual) first; e-commerce/BTYD is Phase 7.

**Proven (P0):** churn-score targeting loses money, worse than random 6/6 seeds;
abstention beats ranking (209 > 718). **(P1):** PIT features prevent a 0.35 AUC
inflation (0.603 vs 0.954). **(P3):** top decile by *value at risk* overlaps top decile
by *churn risk* by only **21%** — the score finds the wrong 79% of the money, before any
causal argument is made.

**Real data (Hillstrom, Criteo, Lenta RCTs).** Worse-than-random did NOT replicate →
claim SCOPED (D-020). **Governing quantity = corr(τ, propensity)** (D-026): Criteo
+0.61→uplift adds 0.6% · Lenta +0.18→10.4% · Hillstrom +0.07→3.9% · churn −0.19→**+107%**.
When orderings coincide the outcome model wins (easier estimand); retention is the
adversarial case. Lenta was an out-of-sample prediction that **landed** (D-031), though
underpowered. Small-n: uplift beats random on **75% of seeds at n=500** (D-023).

---

## Status

**Phases 0-1 and 3 done, 3 real-RCT validations, Phase 2 BUILT + Churn Autopsy report.**
277 tests. CI green. Phase 2 gate (paying client) OPEN.
**Next: Phase 4** — hierarchical Bayesian CATE + abstention. Phase 2's gate needs a
*client*, not code; Phase 3 built the money layer Phase 4 multiplies by.

| # | Phase | Status | Gate |
|---|---|---|---|
| 0 | SubSim + kill test | ✅ **done** | churn-score policy provably loses money |
| 1 | Canonical schema, PIT feature store, ingest | ✅ **done** | leakage suite green in CI |
| 2 | Dunning / involuntary churn + retry-timing model | 🟨 **built** | **first revenue — get a paying client (OPEN)** |
| 3 | Discrete-time survival hazard + CLV | ✅ **done** | beats Cox+RSF 10/10 on Telco, **ties DeepSurv**; best-calibrated (D-049) |
| 4 | Hierarchical Bayesian CATE + abstention | ⬜ | **paper 2**; beats baselines on net revenue at small n |
| 5 | Offer-ladder optimizer + reason codes + dashboard | ⬜ | owner can act without asking us |
| 6 | Holdout infra + incrementality reports + cancel widget | ⬜ | **real client ROI number**; paper 3 |
| 7 | Cross-tenant priors, BTYD router, integrations | ⬜ | tenant #10 beats tenant #1 on day 1 |

**Papers (D-042):** merged 1+2 **drafted** → `papers/paper1/` (read its README first —
§8 abstention is a SPEC, not results; Phase 4 gates it). Lead = corr(τ,propensity) +
small-*n* reliability; simulator is the *instrument*. arXiv → EJOR/DSS, not JMR
(Ascarza's turf). Novelty is NOT "churn scores are bad" — that is Ascarza 2018.
**Go-to-market (D-040/041):** reports before dashboards; report (built) → dunning
autopilot → retention decisions, ordered by *trust required*. Best version is invisible.

---

## Invariants — breaking these invalidates results

1. **Temporal splits only.** Train on months < T, predict at T. Never random split.
   Sole exception: public sets with no calendar time (Telco, GBSG2) — split by
   subject, and say so (D-047).
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
11. **Any split of a person-period frame is by SUBJECT, never by row.** Consecutive
    months of one customer share covariates and an outcome. CI-enforced.
12. **CLV is never extrapolated past the observed tenure support.** `clv()` raises;
    `allow_extrapolation=True` makes the assumption a visible line of code (D-046).

---

## Map

```
keel/core/       schema (occurred_at+available_at) · features (_visible = ONLY data path)
                 leakage (availability audit, time-travel, canary injection)
keel/ingest/     stripe (pure, fixture-tested) · csv_ingest · subsim_adapter
keel/sim/        config · latents (copula) · hazard (ONE defn, two regimes) · subsim
                 counterfactual (exact τ, CRN, LADDER) · calibration · dunning
keel/policy/     dunning — 6 retry policies (processor_default … aggressive)
keel/report/     autopsy (analysis) + render (self-contained HTML)
keel/models/survival/  discrete (person-period hazard + competing risks) · metrics
                 (KM, IPCW Brier, D-calibration — numpy-only so CI runs them) ·
                 baselines (Cox · RSF · DeepSurv, each optional)
keel/models/clv/   value — CLV, value at risk, exact shortfall-by-cause
keel/experiments/  kill_test · leakage_penalty · dunning · survival_benchmark · clv ·
                   figures · survival_figures
keel/benchmarks/   datasets (Hillstrom, Criteo, Lenta) · survival_data (Telco, GBSG2) ·
                   models · evaluate · small_n · spectrum · figures
tests/           277 — fairness, realism, edge cases, leakage gate
explainer/       10 docs for non-technical evaluators/investors (see protocol)
papers/paper1/   merged paper 1+2 draft — README says what is evidence vs. spec
```

## Commands

```bash
make check      # lint + 277 tests + calibration gates — run before every commit
make killtest   # re-run the founding experiment
make survival   # Phase 3 head-to-head (needs `make install-survival` first)
make clv        # value every simulated customer, split the leak by cause
make figures    # regenerate figures, auto-syncs explainer/figures/
make help       # everything else
```
Remote: `origin` → https://github.com/PrashamJ17/PBL-Proj (`main`). CI gates on every
push: tests (3.11-3.13) · calibration · **leakage** · **kill test**.

---

## Update protocol

**Every session — this file:** flip phase status, move **next**, add ONE checkpoint
line. New invariant only if something must never break again. **Detail elsewhere:**
`docs/BUILDLOG.md` (what + tested) · `docs/DECISIONS.md` (why — append D-0NN, never
edit past entries).

**On phase completion — `explainer/`** (non-technical readers): always update
`09-status-and-roadmap.md`; `04`–`08` only if the phase changed what they claim. Zero
assumed knowledge, define every term, **never claim more than was demonstrated** —
those readers cannot check us.

**Then, every checkpoint, no exceptions:**
`make check && git add -A && git commit && git push origin main`.
Message leads with what it **establishes or fixes**, not files touched; numbers in the
body; cite `D-0NN`. Phase completion → `CHANGELOG.md` entry first. Never commit on red —
if blocked, commit *with the failure described*.

Keep under **~150 lines** (raised from 120 at 7 phases / 49 decisions — deliberate, not
drift). If it grows, cut checkpoints first; never invariants.

---

## Checkpoints

Older detail lives in `docs/BUILDLOG.md`; only the current edge is kept here.

- **CP-01…07** — Phases 0-1 (SubSim + kill test; schema, PIT store, leakage, ingest),
  three real-RCT validations (Hillstrom → D-020/023; Criteo → D-024/026; Lenta →
  D-031), Phase 2 dunning (code-aware retries +6.9pp with 32% FEWER attempts;
  `aggressive` strictly dominated — D-033/034), and the Churn Autopsy (D-035/036).
  CI failures fixed: ruff rule set (D-028), pandas timestamps (D-030).
  **Phase 2's gate is a sales task: run the Autopsy against 10 real businesses.**
- **CP-08** — **Phase 3 done** + merged paper drafted. Telco: beats Cox and RSF **10/10
  resplits** on integrated Brier (0.0824 vs 0.0914/0.0964), **ties DeepSurv** (0.0825),
  best-calibrated alongside it; loses GBSG2 to RSF — predicted before running
  (D-021/049). CLV shortfall splits exactly 72.5/27.5. Two metric bugs caught by
  external reference, not by reading (D-048). Below **n=250 nothing reliably beats
  Kaplan-Meier** — unpredicted, most useful number here. The phase bought
  *representation*, not accuracy — say it that way.
