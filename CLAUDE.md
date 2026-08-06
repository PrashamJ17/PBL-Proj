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

---

## Status

**Phase 0 COMPLETE.** 58 tests passing. Both calibration gates green.
**Next: Phase 1** — canonical schema, point-in-time feature store, Stripe ingest,
leakage test suite.

| # | Phase | Status | Gate |
|---|---|---|---|
| 0 | SubSim + kill test | ✅ **done** | churn-score policy provably loses money |
| 1 | Canonical schema, PIT feature store, Stripe ingest | ⬜ **next** | leakage suite green in CI |
| 2 | Dunning / involuntary churn + retry-timing model | ⬜ | **first revenue — get a paying client** |
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

---

## Map

```
keel/sim/config.py         all generative params (documented, sign conventions)
keel/sim/latents.py        8 latent traits; attention~engagement via Gaussian copula
keel/sim/hazard.py         monthly hazard logit — ONE definition, two regimes
keel/sim/subsim.py         lifecycle → person-period panel (observables only)
keel/sim/counterfactual.py exact τ + paired Y(0),Y(1) via common random numbers; LADDER
keel/sim/calibration.py    targets, check(), check_quadrants(), calibrate_intercept()
keel/experiments/kill_test.py  the gate: policies, budget_curve, train_churn_model
keel/experiments/figures.py    figure 1
tests/test_simulator.py    11 tests — fairness + realism
tests/test_edge_cases.py   47 tests — degenerate inputs, boundaries, sign invariants
explainer/                 10 docs for non-technical evaluators/investors (see protocol)
```

## Commands

```bash
make check      # lint + 58 tests + both calibration gates — run before every commit
make killtest   # re-run the founding experiment
make figures    # regenerate figures, auto-syncs explainer/figures/
make help       # everything else
```
Remote: `origin` → https://github.com/PrashamJ17/PBL-Proj (branch `main`).
CI re-runs tests, calibration gates, **and the kill test** on every push.

---

## Update protocol

When finishing a work session:

**Always — this file:**
1. Flip the phase row's status; move **next** marker.
2. Add one CHECKPOINT line below (one line — this file must stay short).
3. Add a new invariant only if something must never be broken again.

**Always — detail elsewhere:** `docs/BUILDLOG.md` (what happened, what was tested),
`docs/DECISIONS.md` (why — append D-0NN, never edit past entries).

**On phase completion — `explainer/` (non-technical: evaluators + investors):**
- `explainer/09-status-and-roadmap.md` — flip the phase row, append a change-log entry.
  **Always update this one.**
- Update others only when the phase changes what they claim:
  `05-the-evidence.md` (new results — and update the honest-status section too),
  `04-what-we-are-building.md` (architecture changed), `06-the-business-case.md`
  (pricing/competitors/traction), `07-risks-and-limitations.md` (risk resolved or found),
  `08-glossary.md` (new term introduced anywhere).
- **Rules for `explainer/`:** zero assumed knowledge, define every term at first use, no
  unexplained jargon, and never claim more than was demonstrated. Overstating there is
  worse than saying nothing — it is read by people who cannot check us.

**Then commit and push — every checkpoint, no exceptions:**
```bash
make check                                   # must pass BEFORE committing
git add -A && git commit && git push origin main
```
- Commit message: lead with what the change **establishes or fixes**, not files touched.
  Put moved numbers in the body. Reference decision IDs (`D-011`) where relevant.
- On phase completion, add a `CHANGELOG.md` entry first (newest first).
- Never commit with failing tests or red calibration gates. If blocked, commit the work
  with the failure described in the message rather than leaving it uncommitted.

Keep this file under ~120 lines. If it grows, cut history, not invariants.

---

## Checkpoints

- **CP-01** — Phase 0 complete. SubSim calibrated (4.5% monthly voluntary churn, 30%
  involuntary share, 17% sleeping dogs, mean τ=−0.010), kill test passed 6/6 seeds,
  figure 1 generated, 58 tests green. Next: Phase 1 canonical schema + PIT store.
