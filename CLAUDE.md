# RetainIQ — project state

**Read this first. Do not re-explore the repo to rediscover state.**
Deeper context only if needed: `docs/DECISIONS.md` (why) · `docs/BUILDLOG.md` (what).

---

## Thesis (do not re-derive)

Churn prediction is a commodity. The unsolved problem is **retention decisioning under
small-sample causal uncertainty**. RetainIQ decides *who to treat, with what, at what cost*
— and **abstains** when the CATE posterior is too wide. Vertical: subscription
(contractual) first; e-commerce/BTYD is Phase 7.

**Proven (P0):** churn-score targeting loses money, worse than random 6/6 seeds;
abstention beats ranking (209 > 718). **(P1):** PIT features prevent a 0.35 AUC
inflation (0.603 vs 0.954). **(P3):** top decile by *value at risk* overlaps top decile
by *churn risk* by only **21%** — the score finds the wrong 79% of the money, before any
causal argument is made.

**Real data (Hillstrom, Criteo, Lenta RCTs).** Worse-than-random did NOT replicate →
claim SCOPED (D-020). **corr(τ, propensity)** (D-026; NOT ours, see D-068), re-run
15 Aug 2026 — use THESE, an older compressed line here had drifted: Hillstrom-mens
+0.69→**−5.6%** · Criteo +0.58→+0.6% · Hillstrom-womens +0.19→+12.7% ·
Lenta +0.17→+20.3% · SubSim churn −0.19→**+106.9%**. Ordering among the positive
points is within noise; the signal is the gap at negative correlation.
When orderings coincide the outcome model wins (easier estimand); retention is the
adversarial case. Lenta was an out-of-sample prediction that **landed** (D-031), though
underpowered. Small-n: best method beats random on **72.5% of 200 draws [.66,.79] at n=500** (D-072).

---

## Status

**Phases 0-1, 3 done. Phase 2 BUILT (gate=client, OPEN). Phases 4-5 BUILT, gates unmet.**
558 tests. CI green.
**Phase 5 COMPLETE**; gate met on its own terms, evidence did NOT improve (58% [.42,.72]).
**Phase 2's delivery path is BUILT (D-062)** — `make preflight` then `make autopsy` on real
CSVs — but its gate is a sales task and **nobody has paid anything**. Next action is
`docs/SALES-RUNBOOK.md`, NOT more modelling.
Watch: **D-057** (Phase 4 multiplied log-odds by money for a whole phase; fixed, losses
-3,531→-1,070, no conclusion changed; 2 of 5 pre-registered predictions FAILED) ·
**D-058** (choosing the offer beats choosing the customer, but 58% is not beating chance —
do NOT tune to close it) · **D-060** (RetainIQ-PBL independently replicated our P1 leakage
result: published ROC-AUC 1.0 is pre-fix, its own code now gives **0.543**).

| # | Phase | Status | Gate |
|---|---|---|---|
| 0 | SubSim + kill test | ✅ **done** | churn-score policy provably loses money |
| 1 | Canonical schema, PIT feature store, ingest | ✅ **done** | leakage suite green in CI |
| 2 | Dunning + retry-timing + **CLI delivery path** | 🟨 **built** | **first revenue — a paying client. STILL OPEN (D-062)** |
| 3 | Discrete-time survival hazard + CLV | ✅ **done** | beats Cox+RSF 10/10 on Telco, **ties DeepSurv**; best-calibrated (D-049) |
| 4 | Hierarchical Bayesian CATE + abstention | 🟨 **built** | gate **PARTIAL** — beats ranking 93% post-D-057, still not do-nothing |
| 5 | Offer-ladder optimizer + reason codes + dashboard | ✅ **done** | owner can act unaided (met); **but** only beats achievable rival 58% [.42,.72] |
| 6 | Holdout infra + incrementality reports | 🟨 **infra BUILT + validated (D-065)** | **real client ROI number** — needs a client |
| 7 | Cross-tenant priors, BTYD router, integrations | ⬜ | tenant #10 beats tenant #1 on day 1 |

**Research/IP plan → `docs/RESEARCH-PLAN.md`** — learning curriculum, the one addition
that would elevate the paper (derive `corr(τ,π)`, do not only measure it), and the IP
call. Repo is PUBLIC and the paper is published (D-066), so the novelty question is settled:
publish, not file — which was the recommendation anyway (Sec 3(k) excludes maths +
business method + program *per se*).

**Published (D-066):** repo is PUBLIC; three cross-linked Zenodo records — paper
`10.5281/zenodo.22009470` · software `10.5281/zenodo.22025879` · data `10.5281/zenodo.22025123`
(concept DOIs; cite these, not version DOIs). `make paper` renders the PDF.
**Patent route in IN/EPO is CLOSED** — publishing the paper was the disclosure. US grace
period to ~19 Aug 2027.

**Papers (D-042):** merged 1+2 **drafted** → `papers/paper1/` (read its README first; §8
REPORTS results + why the gate was unpassable). **Positioning narrowed by D-068:** lead =
pilot size / small-*n* reliability + low-churn regime; simulator is the *instrument*. NOT
ours: "churn scores are bad", harm from risk targeting, the risk–lift correlation (Ascarza
2018, App. A3.4), profit-scored targeting (Lemmens & Gupta 2020). **GTM (D-040/041):** reports
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
14. **A quoted number is what its named command prints TODAY.** Run the command; never copy
    a figure from another document (D-057, D-066, D-069 are all this failure).

---

## Map

```
retainiq/core/       schema (occurred_at+available_at) · features (_visible = ONLY data path)
                 leakage (availability audit, time-travel, canary injection)
retainiq/ingest/     stripe · csv_ingest (alias resolution, recorded defaults, currency) ·
                 preflight (is this export safe? D-062) · subsim_adapter
retainiq/sim/        config · latents (copula) · hazard (ONE defn, two regimes) · subsim
                 counterfactual (exact τ, CRN, LADDER) · calibration · dunning
retainiq/policy/     dunning (6 retry policies) · economics (log-odds→money, D-057) ·
                 ladder (per-customer rung choice, multi-arm pilot, D-058) ·
                 holdout (assignment + ledger + incrementality, D-065)
retainiq/report/     autopsy · render (HTML+print) · reasons (D-059) · worklist (CSV,
                 descriptive only) · dashboard (self-contained, banner-first, D-061)
retainiq/models/uplift/     bayesian (Laplace posterior, validated vs NUTS) · abstention
retainiq/models/survival/  discrete (person-period hazard + competing risks) · metrics
                 (KM, IPCW Brier, D-calibration — numpy-only so CI runs them) ·
                 baselines (Cox · RSF · DeepSurv, each optional)
retainiq/models/clv/   value — CLV, value at risk, exact shortfall-by-cause
retainiq/experiments/  kill_test · leakage_penalty · dunning · survival_benchmark · clv ·
                   abstention (P4 gate) · sensitivity (D-055/056) ·
                   ai_channels (D-064) · holdout_validation (D-065) · figures
retainiq/benchmarks/   datasets (Hillstrom, Criteo, Lenta) · survival_data (Telco, GBSG2) ·
                   models · evaluate · small_n · spectrum · figures
tests/           558 — fairness, realism, edge cases, leakage gate
explainer/       10 docs for non-technical evaluators/investors (see protocol)
papers/paper1/   merged paper 1+2 draft — README says what is evidence vs. spec
```

## Commands

```bash
make check      # lint + 558 tests + calibration gates — run before every commit
make killtest   # re-run the founding experiment
make survival   # Phase 3 head-to-head (needs `make install-survival` first)
make clv        # value every simulated customer, split the leak by cause
make sensitivity # why the Phase 4 gate failed — effect size and offer cost
make ai-channels # can AI outreach drive this? break-even salience (D-064)
make holdout    # Phase 6 — can a small business even measure a campaign? (D-065)
make ladder     # Phase 5 gate — rung-matching vs one good offer
make dashboard  # build the retention dashboard (self-contained HTML)
make preflight ARGS="--customers c.csv --subscriptions s.csv"  # CHECK A CLIENT EXPORT FIRST
make autopsy   ARGS="..."   # then the report
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

Keep under **~245 lines** (raised 120→…→205→215→245 as phases and decisions accumulate —
deliberate, not drift; every raise follows a real trim, this one after compressing six
checkpoints into four to make room for the publication record and its DOIs).
Cut checkpoints; never invariants.

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
- **CP-24** — **Small-n re-run at 200 draws (D-072): 72.5% [.66,.79] at n=500, 84.5% at 1,000,
  95.5% at 2,000.** D-023's 75%/55% were 20 draws no command prints; "55%, a coin flip" is WRONG
  (62.5%). **README, report, explainer, deck, speech STILL QUOTE 75%/55% — correction owed.**
- **CP-23** — **The report assumed rupees and printed "not measured" as 0% (D-071); fixed.**
  Currency belongs to the `Dataset` (export or `--currency`; NEVER assumed; two currencies BLOCK).
  Unmeasured shares are `None`, so formatting one raises. **558 tests in 26 files**.
- **CP-22** — **`make abstention` and `make sensitivity` printed only the PRE-D-057 rule (D-069/070).**
  Both now print corrected first, legacy second; the rule is an argument with NO default. Quoted
  figures held, except: best cheap rung is checkin_call 20% (not nudge 10%); the gate does NOT
  flip in-band once corrected (40% at −5); D-056's hedge reading was partly a bug artefact.
- **CP-21** — **Four papers read in full; novelty narrowed (D-068).** Ascarza 2018 App. A3.4
  simulates corr(RISK, LIFT) (her studies ≈ ±0.2); her Study 2 has risk targeting RAISING churn.
  Profit-scored targeting = Lemmens & Gupta 2020, **not yet a baseline**. Left: pilot size,
  low-churn floor, uplift losing at finite n. **Five points NOT like-for-like** (SubSim = ORACLE
  on TRUE effects); six checks owed. All repo docs, deck, speech, report, explainer corrected; paper text NOT.
- **CP-20/19** — **Deck, storyboard, silent demo video (D-067; `make demo-video`).** Real
  outputs only. AUC 0.700, recall 44.5%, precision 7.4%; **accuracy 79.6% < 96.7% for always
  'stays'** — never a headline. Readiness PER COMPONENT. Live recording caught the demo export
  not producing the quoted numbers — fixed, pinned.
- **CP-18** — **Published; the paper cited itself as its software archive (D-066).** Self-
  referential citations are locally coherent — D-057's shape. **Rule: resolve every identifier,
  never recall it.** `make paper` / `make paper-docx` replace manual exports.
- **CP-17** — **AI outreach priced, not argued (D-064).** Salience harms, not cost per contact,
  so it was SWEPT. **Break-even salience = 0.80, BELOW neutral**: a channel as intrusive as a
  standard offer loses money sent to everyone. At MATCHED salience the AI call DOES win. AI email
  is the best channel — the finding is intrusiveness, not AI. Holdout BEFORE any sender.
- **CP-16** — **The Autopsy can finally be delivered (D-062).** No command took a client CSV
  → report; a real Stripe export failed **4 times in a row**. **`preflight`** — Stripe exports
  CENTS, so a report would quote churn cost at **100x**. It BLOCKS, never converts. `docs/
  SALES-RUNBOOK.md` lists FORBIDDEN claims by experiment. **Gate still open: nobody has paid.**
- **CP-15/14/13** — **Phase 5 built, then shipped (D-058/059/061).** Optimizer makes money
  (28% of oracle vs 13%) but beats the achievable rival on only **58% [.42,.72]** — chance;
  a hindsight uniform rung captures **73%**, so **choosing the offer beats choosing the
  customer**. Reason codes are EXACT, not SHAP. Dashboard: reliability banner first and
  undisableable. RetainIQ-PBL's published ROC-AUC 1.000 is pre-fix; its code gives **0.543**.
- **CP-11** — **The gate was unpassable, and we tested the wrong rung** (D-055/056).
  Break-even |tau|=0.040 vs mean 0.010 → an *oracle* treats only **5.8%**. The two win rates
  move in OPPOSITE directions while sleeping dogs collapse 27%→3%. A minimax-regret reading
  was pre-registered and **REFUTED** out-of-sample.
