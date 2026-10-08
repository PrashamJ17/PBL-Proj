# Pre-registration — the correlation check D-074 left owed

**Written on 8 October 2026, before the check was implemented or run.** Committed on its own,
ahead of the code. The form follows `docs/PREREG-checks-and-baseline.md`.

**What has already been seen.** The thirty-split results in D-074 were on screen when this
was written, and the predictions below are informed by them. That makes this weaker than a
pre-registration written blind. What it still does is fix the design, the comparison and
the reading of each outcome before any of the new numbers exist. No trial split of the new
quantities has been run.

---

## The question D-074 could not answer

D-074 found that fitting risk on customers the effect model never saw moves the
correlation: by 0.11 in Hillstrom (mens) and 0.19 in Hillstrom (womens), where it falls to
−0.01. Two explanations were left tangled together:

- **Shared noise.** When the effect model and the risk model are fitted to the same
  customers, their estimation errors are correlated, and that correlation shows up in the
  figure.
- **Less data.** The independent version gave each model half the training customers. A
  noisier effect estimate correlates less with anything.

And a third thing changed at the same time: the independent risk was fitted on **control
customers only**, where the figure in the table uses **both arms**.

## The design

One new quantity would have answered what D-074 asked for. Two are measured, because one
alone still changes two things at once.

On each split, the training half is cut into parts A and B by the same permutation D-074
used. Four correlations between estimated benefit and estimated risk are then compared.
The first and last already exist; the middle two are new.

| Name | Effect fitted on | Risk fitted on | Risk uses |
|---|---|---|---|
| `pooled` (D-074, the table's figure) | all training customers | the same customers | both arms |
| `pooled_half` (**new**) | part A | part A, the same customers | both arms |
| `pooled_indep` (**new**) | part A | part B, different customers | both arms |
| `control_indep` (D-074) | part A | part B, different customers | control only |

Each step down the table changes one thing:

- `pooled` → `pooled_half`: **the amount of data** halves. Customers are still shared.
- `pooled_half` → `pooled_indep`: **the sharing** is removed. The amount of data is the same.
- `pooled_indep` → `control_indep`: **the definition of risk** changes, from both arms to
  control only (which also halves the rows the risk model sees).

The three steps add up to the gap D-074 reported. Everything else is as in D-074: thirty
splits per setting (seeds 0 to 29), the four real settings and the simulated trial of
60,000, Pearson on the probability scale as the primary figure, with Spearman and the
log-odds scale computed beside it. Means are reported with the 2.5th and 97.5th
percentiles across splits.

The whole command is re-run, not only the new columns, so that every figure it prints
comes from one run. Every column D-074 reported must come out identical to the saved run;
if any does not, that is reported before anything else.

## Predictions

**The mechanism behind C1.** A model fitted on both arms shares estimation noise with
both of the effect model's arm models. To first order the two contributions do not
cancel: what is left is proportional to the outcome's variance under treatment minus its
variance under control. Where treatment raises a response rate that is below one half,
that difference is positive, so sharing customers pushes the correlation **up**. It should
be largest where the treatment effect is largest relative to the sample, which among
these settings is Hillstrom (mens).

| # | Prediction | Refuted if |
|---|---|---|
| **C1** | Sharing customers inflates the figure: `pooled_half` is higher than `pooled_indep` in all four real settings, and the gap is largest in Hillstrom (mens) | it is not higher in any one of the four, or the largest gap is elsewhere |
| **C2** | The instability D-074 found in the Hillstrom figures comes from sharing: in both Hillstrom settings the standard deviation across splits of `pooled_indep` is at most three quarters of that of `pooled_half` | it is more than three quarters in either |
| **C3** | Once the customers are different, the definition of risk matters little: `pooled_indep` and `control_indep` are within 0.10 of each other in all five settings | they differ by more than 0.10 in any |
| **C4** | The simulator's correlation stays negative: `pooled_indep` has a negative mean and is negative on at least 25 of 30 splits | the mean is not negative, or fewer than 25 are |
| **C5** | Criteo stays apart: under `pooled_indep` its interval lies above the upper end of each other real setting's interval, as it did under `control_indep` | its interval overlaps any of the three |

**No prediction is made** about the first step, the effect of halving the data with the
customers still shared. Two forces oppose there: less data means more shared noise, which
by C1 should raise the figure, and a noisier effect estimate, which should lower it. It is
measured and reported.

**C1 is the one with consequences.** If sharing inflates the correlation, the figure in
the project's table, which is `pooled`, overstates it, and by most in the setting that
was already found to be the highest of thirty splits.

## What will be done with the result, fixed now

- If the sharing step moves any real setting by more than **0.05**, the `pooled_indep`
  figure is reported beside `pooled` wherever the table appears, and the text says which
  one is free of shared noise and that it rests on half the data.
- If it moves none by more than 0.05, the table stands as it is and D-074's open question
  is closed with "less data and the definition, not shared noise".
- Either way the three steps are reported for every setting, including any that go
  against the mechanism above.
