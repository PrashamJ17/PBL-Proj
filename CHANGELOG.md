# Changelog

Checkpoint history. One entry per completed phase, newest first.
Technical detail lives in [`docs/BUILDLOG.md`](docs/BUILDLOG.md); the reasoning behind
each choice in [`docs/DECISIONS.md`](docs/DECISIONS.md).

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
