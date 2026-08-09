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

**Phases 0-1, 3 done. Phase 2 BUILT (gate=client, OPEN). Phase 4 BUILT (gate PARTIAL).**
337 tests. CI green.
**Next: Phase 5** — offer ladder + reason codes, with a *specified* first job: make
`alpha` a function of the payoff ratio (D-056). Phase 4's gate is unachievable as written
— beating ranking and beating inaction trade off (D-055) — so do NOT tune Phase 4 to pass
it. The diagnosis is deliberately unfixed; specify the fix before running it.

| # | Phase | Status | Gate |
|---|---|---|---|
| 0 | SubSim + kill test | ✅ **done** | churn-score policy provably loses money |
| 1 | Canonical schema, PIT feature store, ingest | ✅ **done** | leakage suite green in CI |
| 2 | Dunning / involuntary churn + retry-timing model | 🟨 **built** | **first revenue — get a paying client (OPEN)** |
| 3 | Discrete-time survival hazard + CLV | ✅ **done** | beats Cox+RSF 10/10 on Telco, **ties DeepSurv**; best-calibrated (D-049) |
| 4 | Hierarchical Bayesian CATE + abstention | 🟨 **built** | gate **PARTIAL** — beats ranking 65-80%, does NOT beat do-nothing (D-054) |
| 5 | Offer-ladder optimizer + reason codes + dashboard | ⬜ | owner can act without asking us |
| 6 | Holdout infra + incrementality reports + cancel widget | ⬜ | **real client ROI number**; paper 3 |
| 7 | Cross-tenant priors, BTYD router, integrations | ⬜ | tenant #10 beats tenant #1 on day 1 |

**Papers (D-042):** merged 1+2 **drafted** → `papers/paper1/` (read its README first; §8
REPORTS results + why the gate was unpassable). Lead = corr(τ,propensity) + small-*n*
reliability; simulator is the *instrument*. arXiv → EJOR/DSS, not JMR (Ascarza's turf).
Novelty is NOT "churn scores are bad" — that is Ascarza 2018. **GTM (D-040/041):** reports
before dashboards → dunning autopilot → retention decisions, ordered by *trust required*.

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
12. **Never extrapolate past observed support.** Both `clv()` and
    `DiscreteTimeHazard.survival()` raise; `allow_extrapolation=True` makes the
    assumption a visible line of code (D-046, D-050).
13. **Degenerate survival inputs raise errors about the DATA, not the solver** (D-051).
    NaN covariates raise rather than impute — filling is a loader decision.

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
keel/models/uplift/     bayesian (Laplace posterior, validated vs NUTS) · abstention
keel/models/survival/  discrete (person-period hazard + competing risks) · metrics
                 (KM, IPCW Brier, D-calibration — numpy-only so CI runs them) ·
                 baselines (Cox · RSF · DeepSurv, each optional)
keel/models/clv/   value — CLV, value at risk, exact shortfall-by-cause
keel/experiments/  kill_test · leakage_penalty · dunning · survival_benchmark · clv ·
                   abstention (P4 gate) · sensitivity (D-055/056) · figures
keel/benchmarks/   datasets (Hillstrom, Criteo, Lenta) · survival_data (Telco, GBSG2) ·
                   models · evaluate · small_n · spectrum · figures
tests/           337 — fairness, realism, edge cases, leakage gate
explainer/       10 docs for non-technical evaluators/investors (see protocol)
papers/paper1/   merged paper 1+2 draft — README says what is evidence vs. spec
```

## Commands

```bash
make check      # lint + 337 tests + calibration gates — run before every commit
make killtest   # re-run the founding experiment
make survival   # Phase 3 head-to-head (needs `make install-survival` first)
make clv        # value every simulated customer, split the leak by cause
make sensitivity # why the Phase 4 gate failed — effect size and offer cost
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

Keep under **~180 lines** (raised 120→150→165→175→180 as phases, decisions and the paper
accumulated — deliberate, not drift; each raise followed a real trim first). If it grows,
cut checkpoints first; never invariants.

---

## Checkpoints

Older detail lives in `docs/BUILDLOG.md`; only the current edge is kept here.

- **CP-01…07** — Phases 0-1 (SubSim + kill test; schema, PIT store, leakage, ingest), three
  real-RCT validations (Hillstrom D-020/023 · Criteo D-024/026 · Lenta D-031), Phase 2
  dunning (D-033/034), Churn Autopsy (D-035/036), CI fixes (D-028/030). **Phase 2's gate is
  a sales task: run the Autopsy against 10 real businesses.**
- **CP-08** — **Phase 3 done** + merged paper drafted. Telco: beats Cox and RSF 10/10 on
  integrated Brier (0.0824 vs 0.0914/0.0964), **ties DeepSurv** (0.0825); loses GBSG2 to
  RSF as predicted (D-021/049). CLV shortfall 72.5/27.5. Below n=250 nothing beats KM.
- **CP-10** — **Phase 4 built, gate PARTIAL (D-054).** Abstention beats ranking 65-80% of
  draws spending 1/3 as much; beats do-nothing on 0-10%. At alpha=0.05 it treats ZERO and
  correctly returns the baseline — damage prevention, not profit. Pooling cuts losses
  -457→-62 at n=500. Laplace validated vs NUTS (D-053); residual under-coverage is
  empirical Bayes and runs AGAINST the claim.
- **CP-11** — **The gate was unpassable, and we tested the wrong rung** (D-055/056).
  Break-even |τ|=0.040 vs mean 0.010 → an *oracle* treats only **5.8%**; the gate was out
  of reach on arithmetic. Raising the effect DOES flip it at τ=-0.050 (57%) but the two
  win rates move in OPPOSITE directions — never both above chance — while sleeping dogs
  collapse 27%→3%, so passing means deleting the mechanism. Phase 4 also ran on
  `discount_20_3mo` (cost 32, 2nd dearest rung); `feature_nudge` costs 0.10 and pays for
  69%. **Detectability and profitability are anti-correlated across the ladder** — the
  real finding. A minimax-regret reading was pre-registered and **REFUTED** out-of-sample
  (random hedges better, 58.9% vs 85.7%) — recorded, not dropped. It localised a genuine
  defect: best alpha moves 0.49 (nudge) → 0.05 (discount), so **constant alpha is wrong by
  construction**. Left unfixed on purpose → Phase 5. 337 tests.
