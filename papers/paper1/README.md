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
| **8** | **Abstention under posterior uncertainty** | 🟨 **Built and evaluated. Gate PARTIALLY met — beats ranking, does not beat doing nothing (D-054)** |
| 9 | Limitations | Written to match the above |

**Section 8 now reports results, and they are a partial negative.** The rule beats
ranking on 65–80% of draws while spending a third as much, and beats doing nothing on
0–10%. Its `\todo` marker now says exactly that rather than "no results"; do not
soften it. The precursor in Table 1 (`oracle_uplift_abstain`, 209 contacts beating 718)
uses **ground-truth** effects and was always an upper bound on an estimated rule — which
is precisely what the Phase 4 numbers turned out to demonstrate.

**The submission question has changed shape.** The paper now answers "so what should I
do instead?" with a real, tested answer that is honest about its own limits: *abstention
prevents the damage that ranking causes; it does not manufacture profit the data cannot
support*. That is a weaker claim than intended and a more defensible one. A referee who
wanted a positive result will be disappointed; a referee who wanted an honest one will
not.

**Do not fix this by tuning.** The threshold sweep is reported in full, including the
settings where the rule loses money. Selecting the best alpha post hoc, or dropping the
sizes where it fails, is exactly what D-005 and D-011 exist to prevent.

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
| Table 5 (abstention gate) | `python -m keel.experiments.abstention` |
| §8 Laplace-vs-NUTS validation | `python -m keel.models.uplift.mcmc_check` (needs `numpyro`) |
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
