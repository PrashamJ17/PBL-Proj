# Pre-registration — a fixed stopping rule for the benchmark classifier, and which risk the table reports

**Written on 9 October 2026, before the classifier was changed or anything was re-run.**
Committed on its own, ahead of the code. The form follows the two earlier
pre-registrations.

**What has already been seen.** Everything in D-074 and D-076, including the diagnostic
that fitted Hillstrom and the simulated trial with early stopping switched off. So the
Hillstrom and simulator figures below are already known and are listed as checks, not
predictions. **Criteo and Lenta have never been fitted without early stopping.** Those
are the real predictions.

---

## Part 1 — the classifier

### What changes

`benchmarks/models._clf` builds every classifier the benchmarks use. It leaves
scikit-learn's `early_stopping` at its default, which switches on above 10,000 rows
(D-076). It will be set to **off**: every model runs its full 150 rounds whatever the size
of its sample. Nothing else about the classifier changes.

**Why off, and not always on.** Either would make a T-learner's two models stop by the
same rule. Always-on would hold back a tenth of every sample, including samples of 500,
and would change every small-sample result in the project. Off changes nothing that was
fitted on 10,000 rows or fewer, because nothing there ever stopped early.

**What it costs.** A model that would have stopped at round 60 now runs to 150. On a small
signal that is some overfitting. It is the same overfitting for both arms, which is the
point.

### What is re-run

- `make correlation-checks`: thirty splits of all five settings, every column.
- `make small-n`: 200 draws, the project's lead result.

### Checks (already known, must reproduce)

| # | Check | Fails if |
|---|---|---|
| **K1** | The two Hillstrom rows and the simulator row reproduce the diagnostic's "stopping off" figures to the last digit: `pooled` +0.30 [+0.17, +0.42], +0.16 [+0.04, +0.31], −0.22 [−0.33, −0.07] | any differs |
| **K2** | `make small-n` gives the same win rates as the run on record at every training size up to 10,000: 72.5%, 84.5%, 95.5%, 98.5%, 100% for the best method, 62.5% for the weakest at 500 | any differs |

### Predictions (Criteo and Lenta, never fitted this way)

| # | Prediction | Refuted if |
|---|---|---|
| **S1** | The table's figure (`pooled`, Pearson, probability scale) moves by less than 0.05 in Criteo and in Lenta. With several hundred thousand rows per model, the round at which a model stops should matter little | it moves by 0.05 or more in either |
| **S2** | Their spread across splits does not grow: the standard deviation of `pooled` is no more than 1.25 times what it was (0.044 and 0.056) | it is more than 1.25 times in either |
| **S3** | The scale finding survives: the correlation is lower on the log-odds scale than on the probability scale in all four real settings | it is not lower in any one |
| **S4** | What the uplift model gains does not change in kind: in each of the four real settings the range across splits includes zero, and in the simulator the gain is positive on at least 27 of 30 splits | either part fails |
| **S5** | With customers kept separate, control-only risk reads lower than both-arm risk in all four real settings, and by at least 0.05 in Criteo | it is not lower in any one, or by less than 0.05 in Criteo |
| **S6** | The small-sample result at the largest training size, 20,000, where some models did stop early, stays at 99% or above for the best method | it falls below 99% |

**S1 is the one that could embarrass the table.** If the Criteo or Lenta figure moves a
long way, then the table's two largest experiments were also being shaped by where their
models happened to stop, and D-074's reading of them goes the way of its reading of
Hillstrom.

---

## Part 2 — which risk the table reports

D-076 found that the definition of risk moves the figure more than shared noise does. The
table has so far led with risk fitted on **both arms, on the same customers as the effect
model**. That figure has two things wrong with it as a measurement of Ascarza's quantity:

- **It is not her definition.** Her RISK is the chance of the outcome for a customer who is
  left alone, so it is fitted on control customers. A model fitted on both arms has seen
  treated customers too. Its prediction is roughly the untreated risk plus the treated
  share of the effect, so it carries part of the effect inside it, and correlates with the
  effect for that reason alone whenever the effect varies between customers.
- **It shares estimation noise with the effect model** (D-076, by up to 0.07 with stopping
  held fixed).

### What changes, fixed now

- **The headline figure becomes `control_indep`**: risk fitted on control customers only,
  on customers the effect model never saw. It is her definition and it is free of shared
  noise. It rests on half the training data for each model, which the documents will say.
- The both-arm, same-customer figure stays in the table beside it, labelled as the earlier
  definition, so that nothing reported before disappears.
- The figure (`fig07`) plots the headline figure on both scales.
- No new estimator is introduced. Every column already exists.

### What is not claimed in advance

No prediction is made about whether the headline figure "looks better" or "looks worse"
for the project. It is lower than the both-arm figure in every real setting already
measured. It is reported because it is the right quantity, and the both-arm figure stays
beside it so the difference can be seen.

---

## What will be done with the results

- If K1 or K2 fails, the change is not what it was meant to be. It is reverted and the
  failure is reported before anything else.
- If S1 or S2 fails, the Criteo or Lenta rows are reported under both stopping rules, as
  the Hillstrom rows were in D-076, and D-074's reading of them is revisited in the open.
- The classifier's setting becomes a project invariant with a test, so that a T-learner's
  two models can never again be fitted by different rules without a failing test.
- Documents are corrected to the new table. The paper is written from it.
