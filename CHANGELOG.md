# Changelog

Checkpoint history. One entry per completed phase, newest first.
Technical detail lives in [`docs/BUILDLOG.md`](docs/BUILDLOG.md); the reasoning behind
each choice in [`docs/DECISIONS.md`](docs/DECISIONS.md).

---

## Phase 1 — Canonical schema, point-in-time features, ingest

**Making it structurally impossible to train on information that did not exist yet.**

### Added

- **Canonical schema** (`keel/core/schema.py`) — six timestamp-native tables. Every
  fact carries both `occurred_at` (when it happened) and `available_at` (when it became
  knowable). Includes `interventions`, the holdout ledger no competitor keeps.
- **Point-in-time feature store** (`keel/core/features.py`) — 15 features, with the
  leakage guarantee enforced structurally: one gate function, no other path to the data.
- **Leakage suite** (`keel/core/leakage.py`) — availability audit, time-travel
  consistency, and adversarial canary injection.
- **Ingest adapters** — Stripe (pure, fixture-tested, no API key), CSV (the Churn
  Autopsy path), and SubSim → canonical for end-to-end testing.

### Results — the leakage penalty

Same features, built three ways:

| vintage | apparent AUC | what it is |
|---|---:|---|
| `correct` | **0.603** | filters on `available_at` |
| `occurred_only` | 0.613 | ignores settlement lag — the subtle bug |
| `no_filter` | **0.954** | no temporal filter — the catastrophic bug |

**0.954 vs 0.603.** "Total sessions ever" looks innocent, but a customer who churned in
month 4 generates no rows afterwards, so the feature encodes the outcome. The model
appears excellent and has learned only who stopped producing data.

That 0.35 gap is not performance. It is how far a backtest would have overstated the
model before production — and the number a business would have staked a budget on.

### Notable

- **The leakage suite is required to have teeth** (D-017). It must *fail* on
  deliberately leaked vintages and *catch* a planted canary, while not flagging honest
  features. A suite that has never caught a leak is evidence of nothing.
- Unsafe feature modes exist **on purpose** (D-016), so the safeguard's value is
  measured rather than asserted. Default is safe; a test enforces it.
- Stripe mapping handles the three things that are quietly wrong everywhere:
  zero-decimal currencies, interval normalisation, and `canceled_at` ≠ `ended_at`.

### Fixed

- `scikit-learn` was declared only in an optional extra despite being imported by the
  Phase 0 kill test — a fresh install would have failed.
- Tests only passed under `python -m pytest`; bare `pytest` could not import the
  package.

**137 tests passing.** CI gained a leakage gate alongside the calibration and kill-test
gates.

---

## Phase 0 — SubSim and the kill test

**The founding claim was tested and survived.**

### Added

- **SubSim** (`keel/sim/`) — a subscription-business simulator emitting *exact*
  ground-truth counterfactuals: both potential outcomes per customer, which no real
  dataset can provide.
- **Kill test** (`keel/experiments/kill_test.py`) — the go/no-go experiment on the
  project's central thesis.
- **Figure 1** (`papers/figures/fig01_kill_test.png`) — outcome and mechanism.
- 58 tests, calibration gates, and full documentation
  (`docs/`, `explainer/`, `CLAUDE.md`).

### Results — 6/6 seeds, unanimous

| Finding | Detail |
|---|---|
| Churn-score targeting loses money | −22,123 at 20% budget |
| **It is worse than random targeting** | random −17,035 vs churn-score −26,903 (mean) |
| **Abstention beats ranking** | 209 contacts (+8,610) earned more than 718 (+5,877) |
| Mechanism | Sleeping dogs are 48% of the top risk decile vs 2% of the bottom |

A more accurate churn model makes this *worse* — accuracy at detecting disengagement
means precision at finding sleeping dogs.

### Calibration

Matched to published 2026 SMB-SaaS benchmarks and stable across 8 seeds: 4.5% monthly
voluntary churn, 30% involuntary share, 23% two-year retention, 2.0× early-to-late
hazard ratio.

### Notable

- **An earlier, more favourable result was rejected.** The first configuration produced
  30% sleeping dogs and a *harmful* average treatment effect, making the headline
  trivially true and not credible. Reconfigured so the offer **helps on average**
  (mean τ = −0.010), making the claim harder to demonstrate. It held anyway (D-011).
- The churn baseline is a real gradient-boosted model on observables with a strict
  temporal split (AUC ≈ 0.70), not a strawman (D-012).
- Calibration targets were found **mutually inconsistent** and corrected — 30–60%
  two-year retention cannot coexist with a 3–7% voluntary churn band (D-006).
