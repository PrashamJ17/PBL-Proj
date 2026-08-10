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

**Phases 0-1, 3 done. Phase 2 BUILT (gate=client, OPEN). Phases 4-5 BUILT, gates unmet.**
388 tests. CI green.
**Phase 5 COMPLETE** (optimizer + reason codes + dashboard). Its gate is met *on its own
terms* — an owner can act unaided — but the evidence did NOT improve: still 58% [.42,.72].
**Next: Phase 2's gate (a paying client) or Phase 6 holdout infra — NOT more modelling.** **D-057: Phase 4 multiplied log-odds by money for a whole phase** — fixed in
`keel/policy/economics.py`, losses -3,531→-1,070, but NO qualitative conclusion changed;
predictions were pre-registered (`docs/PREREG-phase5.md`) and 2 of 5 FAILED.
**D-058: choosing the offer beats choosing the customer** — but 58% [.42,.72] is not
beating chance. Do NOT tune to close it. **D-060:** sibling project RetainIQ independently
replicated our P1 leakage result — its published ROC-AUC 1.0 is pre-fix; re-running its
own code gives **0.543**, worse than "always predict churn".

| # | Phase | Status | Gate |
|---|---|---|---|
| 0 | SubSim + kill test | ✅ **done** | churn-score policy provably loses money |
| 1 | Canonical schema, PIT feature store, ingest | ✅ **done** | leakage suite green in CI |
| 2 | Dunning / involuntary churn + retry-timing model | 🟨 **built** | **first revenue — get a paying client (OPEN)** |
| 3 | Discrete-time survival hazard + CLV | ✅ **done** | beats Cox+RSF 10/10 on Telco, **ties DeepSurv**; best-calibrated (D-049) |
| 4 | Hierarchical Bayesian CATE + abstention | 🟨 **built** | gate **PARTIAL** — beats ranking 93% post-D-057, still not do-nothing |
| 5 | Offer-ladder optimizer + reason codes + dashboard | ✅ **done** | owner can act unaided (met); **but** only beats achievable rival 58% [.42,.72] |
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
keel/policy/     dunning (6 retry policies) · economics (log-odds→money, D-057) ·
                 ladder (per-customer rung choice, multi-arm pilot, D-058)
keel/report/     autopsy · render (HTML) · reasons (exact attribution, D-059) ·
                 dashboard (self-contained, banner-first, D-061)
keel/models/uplift/     bayesian (Laplace posterior, validated vs NUTS) · abstention
keel/models/survival/  discrete (person-period hazard + competing risks) · metrics
                 (KM, IPCW Brier, D-calibration — numpy-only so CI runs them) ·
                 baselines (Cox · RSF · DeepSurv, each optional)
keel/models/clv/   value — CLV, value at risk, exact shortfall-by-cause
keel/experiments/  kill_test · leakage_penalty · dunning · survival_benchmark · clv ·
                   abstention (P4 gate) · sensitivity (D-055/056) · figures
keel/benchmarks/   datasets (Hillstrom, Criteo, Lenta) · survival_data (Telco, GBSG2) ·
                   models · evaluate · small_n · spectrum · figures
tests/           388 — fairness, realism, edge cases, leakage gate
explainer/       10 docs for non-technical evaluators/investors (see protocol)
papers/paper1/   merged paper 1+2 draft — README says what is evidence vs. spec
```

## Commands

```bash
make check      # lint + 388 tests + calibration gates — run before every commit
make killtest   # re-run the founding experiment
make survival   # Phase 3 head-to-head (needs `make install-survival` first)
make clv        # value every simulated customer, split the leak by cause
make sensitivity # why the Phase 4 gate failed — effect size and offer cost
make ladder     # Phase 5 gate — rung-matching vs one good offer
make dashboard  # build the retention dashboard (self-contained HTML)
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

Keep under **~205 lines** (raised 120→150→165→175→180→195→205 as phases, decisions and
the paper accumulated — deliberate, not drift; every raise follows a real trim, this one
after merging CP-08/10 and compressing CP-01…07/11/14). Cut checkpoints; never invariants.

---

## Checkpoints

Older detail lives in `docs/BUILDLOG.md`; only the current edge is kept here.

- **CP-01…07** — Phases 0-1, three real-RCT validations (Hillstrom D-020/023 · Criteo
  D-024/026 · Lenta D-031), Phase 2 dunning + Autopsy (D-033/036), CI fixes (D-028/030).
  **Phase 2's gate is a sales task: run the Autopsy against 10 real businesses.**
- **CP-08/10** — **Phase 3 done** (Telco: beats Cox/RSF 10/10 on integrated Brier, **ties
  DeepSurv**; loses GBSG2 as predicted, D-021/049; n<250 KM wins) + paper drafted.
  **Phase 4 built, gate PARTIAL (D-054):** beats ranking 65-80% spending 1/3 as much,
  do-nothing 0-10%. Laplace validated vs NUTS (D-053); under-coverage runs AGAINST us.
- **CP-12** — **D-057: a units bug ran for a whole phase.** `decide` multiplied a
  **log-odds** tau by CLV as if it were a probability difference — believed -104.5 where
  truth was +20.5. Overstatement `1/(p0(1-p0))` → **worst for low-risk customers**: the
  Sure Thing error, inside our own rule. Every test passed: all were self-consistency
  checks, and a units error is self-consistent. Fixed in `policy/economics.py`; the new
  rule takes **money only**, so it is unrepresentable. Losses -3,531→-1,070, beats
  ranking 93%. **2 of 5 pre-registered predictions FAILED** — no cheap rung passes; alpha
  spread did not shrink, so **D-056 survives a challenge we raised ourselves**. Necessary,
  not sufficient: `corr(tau_hat, tau_true)=0.13`.
- **CP-15** — **Dashboard shipped; Phase 5 done (D-061).** Self-contained HTML, no
  server, no new dep — Streamlit/Next.js rejected (invariant 7; a runtime for a project
  whose gate is still "does it earn"). **Reliability banner is FIRST and cannot be
  disabled**: the inverse of a dashboard shouting "SAVE NOW" over a 0.543 model (D-060).
  Looking at the render (not the tests) caught a **47%-confidence 1,972 discount** ranked
  4th — sub-60% rows now flag inline. Verified both themes in-browser (D-038). 388 tests.
- **CP-14** — **Reason codes (D-059) + RetainIQ compared (D-060).** Attribution is
  EXACT not SHAP: `tau` is linear so contribution = `gamma_j*xs_ij`, no dependency.
  Explains the *decision* (`-Δp*V - c`, and why this rung) not the prediction; says
  "nothing specific to this customer drives it" when sigma_gamma collapses, and carries
  D-058's 58% on every line. Ran RetainIQ's own pipeline: published ROC-AUC **1.000** is
  pre-leakage-fix, actual **0.543** — worse than "always predict churn". **Independent
  replication of P1.**
- **CP-13** — **Phase 5 optimizer built; gate UNMET (D-058).** Per-rung effects from a
  multi-arm pilot (~35/arm at n=500), pooled across rungs via D-041 machinery. First
  estimated policy here to make money (655/1,039/2,252): **28% of oracle vs 13%** for the
  achievable rival — but beats it on only **58% [.42,.72]**, chance. **Sellable finding:
  pilot-pick matches the true best rung 13% of the time** (random=17%) and loses money at
  n=1000, while a hindsight uniform rung captures **73%** vs the optimizer's 28%.
  **Choosing the offer beats choosing the customer.** Risk aversion HURT. 357 tests.
- **CP-11** — **The gate was unpassable, and we tested the wrong rung** (D-055/056).
  Break-even |τ|=0.040 vs mean 0.010 → an *oracle* treats only **5.8%**. Raising the
  effect flips it at τ=-0.050 but the two win rates move in OPPOSITE directions — never
  both above chance — while sleeping dogs collapse 27%→3%, so passing deletes the
  mechanism. **Detectability and profitability are anti-correlated across the ladder** —
  the real finding. A minimax-regret reading was pre-registered and **REFUTED**
  out-of-sample (random hedges better). Localised: best alpha moves 0.49→0.05, so
  **constant alpha is wrong by construction**.
