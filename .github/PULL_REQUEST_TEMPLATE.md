## What this changes

<!-- Lead with what it establishes or fixes, not which files moved. -->

## Why

<!-- If this changes a modelling choice, link the D-0NN entry in docs/DECISIONS.md. -->

## Results affected

<!-- If any headline number moved, put the before/after here. Otherwise "none". -->

---

## Checklist

- [ ] `make check` passes locally (lint + tests + calibration gates)
- [ ] No latent trait reaches the observable panel
- [ ] Temporal splits only — no random splitting of customer records
- [ ] If a hazard coefficient or latent distribution changed, `calibrate_intercept` was
      re-run and the new value committed
- [ ] `mean_tau` is still negative (the offer still helps on average)

If the simulator changed:

- [ ] `docs/DECISIONS.md` — new appended entry, past entries untouched
- [ ] `docs/BUILDLOG.md` — what changed and the measured effect
- [ ] `explainer/` updated if any claim shown to non-technical readers moved
