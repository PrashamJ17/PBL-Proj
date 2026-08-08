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

**Real data (Hillstrom, Criteo, Lenta RCTs).** Worse-than-random did NOT replicate →
claim SCOPED (D-020). **Governing quantity = corr(τ, propensity)** (D-026): Criteo
+0.61→uplift adds 0.6% · Lenta +0.18→10.4% · Hillstrom +0.07→3.9% · churn −0.19→**+107%**.
When orderings coincide the outcome model wins (easier estimand); retention is the
adversarial case. Lenta was an out-of-sample prediction that **landed** (D-031), though
underpowered. Small-n: uplift beats random on only **75% of seeds at n=500** (D-023).

---

## Status

**Phases 0-1 done, 3 real-RCT validations, Phase 2 BUILT + Churn Autopsy report.**
223 tests. CI green. Phase 2 gate (paying client) OPEN.
**Next: Phase 3** — survival hazard + CLV. Phase 2's gate needs a *client*, not code.

| # | Phase | Status | Gate |
|---|---|---|---|
| 0 | SubSim + kill test | ✅ **done** | churn-score policy provably loses money |
| 1 | Canonical schema, PIT feature store, ingest | ✅ **done** | leakage suite green in CI |
| 2 | Dunning / involuntary churn + retry-timing model | 🟨 **built** | **first revenue — get a paying client (OPEN)** |
| 3 | Discrete-time survival hazard + CLV | ⬜ | beats Cox/RSF/DeepSurv on public data; calibrated |
| 4 | Hierarchical Bayesian CATE + abstention | ⬜ | **paper 2**; beats baselines on net revenue at small n |
| 5 | Offer-ladder optimizer + reason codes + dashboard | ⬜ | owner can act without asking us |
| 6 | Holdout infra + incrementality reports + cancel widget | ⬜ | **real client ROI number**; paper 3 |
| 7 | Cross-tenant priors, BTYD router, integrations | ⬜ | tenant #10 beats tenant #1 on day 1 |

**Papers (D-042):** merge 1+2 → small-*n* abstention + the corr(τ,propensity)
principle; simulator is the *instrument*, finding is the lead. arXiv → EJOR/DSS, not
JMR (Ascarza's turf). Novelty is NOT "churn scores are bad" — that is Ascarza 2018.

**Go-to-market (D-040/041):** reports before dashboards. Three usage modes: report
(built) → dunning autopilot → retention decisions. Dunning is first because it needs
the *least trust*, not because it is easiest. The best version is invisible.

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
keel/core/       schema (occurred_at+available_at) · features (_visible = ONLY data path)
                 leakage (availability audit, time-travel, canary injection)
keel/ingest/     stripe (pure, fixture-tested) · csv_ingest · subsim_adapter
keel/sim/        config · latents (copula) · hazard (ONE defn, two regimes) · subsim
                 counterfactual (exact τ, CRN, LADDER) · calibration · dunning
keel/policy/     dunning — 6 retry policies (processor_default … aggressive)
keel/report/     autopsy (analysis) + render (self-contained HTML)
keel/experiments/  kill_test · leakage_penalty · dunning · figures
keel/benchmarks/   datasets (Hillstrom, Criteo, Lenta) · models · evaluate
                   small_n · spectrum (when uplift pays) · figures
tests/                     223 tests — fairness, realism, edge cases, leakage gate
explainer/                 10 docs for non-technical evaluators/investors (see protocol)
```

## Commands

```bash
make check      # lint + 223 tests + calibration gates — run before every commit
make killtest   # re-run the founding experiment
make figures    # regenerate figures, auto-syncs explainer/figures/
make help       # everything else
```
Remote: `origin` → https://github.com/PrashamJ17/PBL-Proj (`main`). CI gates on every
push: tests (3.11-3.13) · calibration · **leakage** · **kill test**.

---

## Update protocol

**Every session — this file:** flip phase status, move **next**, add ONE checkpoint
line. New invariant only if something must never break again.
**Detail elsewhere:** `docs/BUILDLOG.md` (what + tested) · `docs/DECISIONS.md`
(why — append D-0NN, never edit past entries).

**On phase completion — `explainer/`** (non-technical readers): always update
`09-status-and-roadmap.md`; update `04`/`05`/`06`/`07`/`08` only if the phase changed
what they claim. Rules: zero assumed knowledge, define every term, **never claim more
than was demonstrated** — those readers cannot check us.

**Then, every checkpoint, no exceptions:**
```bash
make check && git add -A && git commit && git push origin main
```
Message leads with what it **establishes or fixes**, not files touched; numbers in the
body; cite `D-0NN`. Phase completion → `CHANGELOG.md` entry first. Never commit on red —
if blocked, commit *with the failure described*.

Keep this file under **~150 lines** (raised from 120 once the project reached 7 phases,
42 decisions and 3 real datasets — a deliberate change, not drift). If it grows past
that, cut checkpoint history first; never invariants.

---

## Checkpoints

Older detail lives in `docs/BUILDLOG.md`; only the current edge is kept here.

- **CP-01…05** — Phases 0-1 (SubSim + kill test; schema, PIT store, leakage, ingest)
  and three real-RCT validations (Hillstrom → D-020/023; Criteo → D-024/026;
  Lenta → D-031). Two CI failures fixed: unpinned ruff rule set (D-028), pandas
  timestamp resolution (D-030).
- **CP-06** — Phase 2 dunning BUILT. Code-aware retries +6.9pp with 32% FEWER attempts;
  `aggressive` strictly dominated (D-033 — a test caught the sim inflating its own
  result). Calibrated on the passive band, reproduces the dedicated band un-tuned
  (D-034). **Gate (paying client) OPEN — a sales task, not a code task.**
- **CP-07** — Churn Autopsy built (`keel/report/`): billing CSV in, self-contained HTML
  out. Findings badged measured-vs-estimated (D-035); refuses to name targets (D-036).
  Fixed: recovery read 0% (D-037), chart text invisible in dark mode (D-038/039).
  223 tests. **Next action is NOT code: run the Autopsy against 10 real businesses.**
