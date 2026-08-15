# Contributing

Thanks for looking. This is a research project with a commercial thesis attached, so a
few of the rules below are unusual — they exist to protect the validity of results, not
to police style.

## Setup

```bash
git clone https://github.com/PrashamJ17/PBL-Proj.git
cd PBL-Proj
make install
make check      # lint + tests + calibration gates
```

## Before you open a pull request

```bash
make check
```

CI runs the same thing plus the kill test across three seeds.

---

## Rules that are not negotiable

These are invariants. Breaking any of them silently invalidates results, which is worse
than breaking the build.

**1. Temporal splits only.** Train on months `< T`, predict at `T`. Never split customer
records randomly — that leaks the future into the past and inflates every metric.

**2. Latents must never reach the observable panel.** `SimResult.latents` and
`SimResult.hidden_state` are oracle-only. A model that sees them is reading the answer
key. Enforced by `test_latents_do_not_leak_into_panel`.

**3. Never hand-tune the hazard intercept.** Run `calibration.calibrate_intercept` after
changing *any* hazard coefficient or latent distribution. Hand-tuning a generative
process is how you accidentally fit it to flatter your own method.

**4. `mean_tau` must stay negative.** The offer must help on average. If it becomes
harmful, the headline result turns trivially true and stops being credible. The
calibration gate fails the build if this happens.

**5. Voluntary and involuntary churn stay separate.** Never sum them into one outcome.

**6. Value is measured against doing nothing** — never save-rate-among-treated, which is
contaminated by selection.

**Read [`docs/DECISIONS.md`](docs/DECISIONS.md) before changing a modelling choice.**
Several decisions there deliberately make the project's central claim *harder* to
demonstrate. If a change appears to make results better, check it is not undoing one of
those on purpose.

---

## Changing the simulator

Any change to `retainiq/sim/` requires:

1. `make calibrate` still passes — both gates.
2. Calibration is stable across seeds (`sweep_seeds`), not just the default one.
3. A new entry appended to `docs/DECISIONS.md` explaining *why*, including the
   alternative you rejected. Never edit past entries.
4. A note in `docs/BUILDLOG.md` recording what changed and what the measured effect was.

If a change alters a headline number, `explainer/09-status-and-roadmap.md` and
`explainer/05-the-evidence.md` need updating too — including their honest-status
sections.

---

## Style

- `ruff` handles formatting and linting. `make fmt` fixes most things.
- Comments should explain *why*, not *what*. The code says what.
- Docstrings on any function whose correctness is not obvious from its signature —
  especially anything touching causal logic.

## Commit messages

Lead with what the change *establishes* or *fixes*, not what files it touches. If a
result changed, put the numbers in the body. Reference decision IDs (`D-011`) where
relevant.

## Reporting a problem

If you think a result is wrong, that is the most valuable issue you can file. Include the
seed, the config, and what you expected. There is an issue template for it.
