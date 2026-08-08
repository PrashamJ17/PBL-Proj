# Paper 1+2 (merged) — draft status

Positioning is settled in `docs/DECISIONS.md` **D-042**: papers 1 and 2 are merged, the
simulator is the *instrument* rather than the contribution, and the lead is the
`corr(τ, propensity)` principle plus small-*n* abstention. The novelty is **not**
"churn scores are bad" — that is Ascarza (2018, *JMR*) and a paper led by it gets desk
rejected with that citation.

**Target:** arXiv preprint immediately (priority, and it doubles as lead generation),
then *EJOR* or *Decision Support Systems*. **Not** *JMR* — Ascarza's home turf, and it
would want field experiments we do not have.

```
main.tex   the draft
refs.bib   bibliography
```

Not compiled here — this environment has no TeX installation. `latexmk -pdf main.tex`.

---

## What is evidence-backed and what is not

This is the part to read before showing the draft to anyone.

| § | Section | Status |
|---|---|---|
| 3 | The decision problem | Definitions only |
| 4 | The instrument (SubSim, kill test, leakage) | ✅ Implemented, tested, reproducible |
| 5 | `corr(τ, π)` governs whether uplift pays | ✅ Four real datasets + simulator |
| 6 | Reliability at small *n* | ✅ Real data (Hillstrom), evaluation set held fixed |
| 7 | From probability to money (survival + CLV) | ✅ Phase 3, 10 resplits, public data |
| **8** | **Abstention under posterior uncertainty** | ❌ **SPECIFICATION ONLY — Phase 4 not built** |
| 9 | Limitations | Written to match the above |

**Section 8 carries a `\todo` marker in the source and says in its own first line that
it reports no results.** Do not remove that marker until Phase 4 exists. The paper as it
stands is a diagnosis with a proposed treatment, and the abstract, the conclusion and
the limitations section all say so. The precursor result in Table 1
(`oracle_uplift_abstain`, 209 contacts beating 718) uses **ground-truth** effects and is
an upper bound on what an estimated rule can achieve — it is not evidence for one, and
the draft states that explicitly.

**A submission decision, not a drafting one:** whether to submit without Section 8 is
open. Submitting the diagnosis alone is defensible (Sections 5 and 6 stand on their own
and Section 6 is the strongest real-data result in the project), but the referee
question "so what should I do instead?" is then unanswered by anything but a
specification.

---

## Regenerating every number

Run from the repository root. Anything in the paper not produced by one of these is a
bug in the paper.

| Paper location | Command |
|---|---|
| Table 1 (kill test) | `make killtest` |
| §4 calibration aggregates | `make calibrate` |
| §4 leakage penalty (0.603 / 0.613 / 0.954) | `python -m keel.experiments.leakage_penalty` |
| Table 2 (`corr(τ, π)`, 5 settings) | `python -m keel.benchmarks.spectrum` |
| Table 3 (small-*n* win rates) | `python -m keel.benchmarks.small_n` |
| §5 Hillstrom / Criteo / Lenta headline figures | `python -m keel.benchmarks.run` |
| Table 4 (Telco survival head-to-head) | `make survival` |
| §7 CLV, 21% decile overlap, 72.5/27.5 split | `make clv` |
| Figures 1–5 | `make figures` |

The benchmark commands need the public datasets in `data/` (Hillstrom and Telco
download automatically; Criteo and Lenta are large and are fetched by the loaders' own
instructions). `make survival` needs the Phase 3 extras: `make install-survival`.

---

## Before submission

- [ ] **Verify every bibliography locator.** `refs.bib` omits page ranges it could not
      confirm rather than guessing, and marks the entries most likely to need checking.
      Two are working papers or white papers whose canonical form should be re-checked.
- [ ] Confirm the preferred citation for the Lenta dataset with the `scikit-uplift`
      maintainers.
- [ ] Re-run every command in the table above and diff the numbers against the draft.
      Two metric bugs (D-048) changed Phase 3 numbers *after* they were first written
      down; assume it can happen again.
- [ ] Decide the Section 8 question above.
- [ ] Check the prior-art sweep is still current — in particular Verbeke et al. on
      cost-sensitive causal decision-making, which is the closest work to Section 8 and
      is also a target venue.
- [ ] arXiv category: `stat.AP` primary, `cs.LG` cross-list.

## Honest self-assessment

The strongest thing here is Section 6: real data, a metric the field does not use
(reliability rather than expectation), and a result that is uncomfortable for the
literature it comes from. The second strongest is the Lenta prediction in Section 5,
because it was recorded before the data was obtained and could have failed.

The weakest is that every negative-correlation observation comes from our own
simulator. We argue the mechanism is real and generative rather than fitted, but a
public retention experiment containing it would be worth more than any additional
analysis of the ones we have. Finding or running one is the highest-value thing that
could happen to this paper.
