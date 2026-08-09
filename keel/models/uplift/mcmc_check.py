"""Validate the Laplace posterior against NUTS.

`HierarchicalCATE` approximates the coefficient posterior with a Gaussian at the mode.
That is a choice made for speed and for keeping the estimator on numpy, and it is not
self-evidently adequate at the sample sizes this project cares about. A logistic
posterior at n = 250 is skewed, and a Gaussian fitted at its mode is narrower than the
thing it approximates.

This module fits the *same model* with NUTS and compares. It is the same discipline the
survival metrics use against lifelines and scikit-survival (D-048): an implementation
is checked against an independent one rather than against its own intuition.

Not imported by the estimator and not run in CI -- numpyro and jax are optional extras.
The finding it produced is recorded in D-053 and acted on in `bayesian.py`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def nuts_posterior(
    X: pd.DataFrame | np.ndarray,
    t: np.ndarray,
    y: np.ndarray,
    sigma_gamma_prior: float = 1.0,
    prior_sd_beta: float = 1.0,
    prior_sd_tau0: float = 2.5,
    num_warmup: int = 500,
    num_samples: int = 1000,
    seed: int = 0,
) -> dict[str, np.ndarray]:
    """Sample the same model with NUTS.

    `sigma_gamma` is given a half-normal hyperprior and sampled rather than fixed,
    which is the fully Bayesian version of the empirical-Bayes grid the Laplace path
    uses. Returns per-customer posterior draws of `tau_i`.
    """
    import jax
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist
    from numpyro.infer import MCMC, NUTS

    A = np.asarray(X, dtype=float)
    Xs = (A - A.mean(axis=0)) / np.maximum(A.std(axis=0), 1e-9)
    n, p = Xs.shape

    def model(Xs, t, y=None):
        alpha = numpyro.sample("alpha", dist.Normal(0.0, 10.0))
        beta = numpyro.sample("beta", dist.Normal(0.0, prior_sd_beta).expand([p]))
        tau0 = numpyro.sample("tau0", dist.Normal(0.0, prior_sd_tau0))
        # Sampled, not fixed: this is what the Laplace path approximates with a
        # weighted grid.
        sigma_g = numpyro.sample("sigma_gamma", dist.HalfNormal(sigma_gamma_prior))
        gamma = numpyro.sample("gamma", dist.Normal(0.0, 1.0).expand([p]))
        gamma = gamma * sigma_g

        tau = tau0 + Xs @ gamma
        eta = alpha + Xs @ beta + t * tau
        numpyro.sample("obs", dist.Bernoulli(logits=eta), obs=y)

    kernel = NUTS(model)
    mcmc = MCMC(kernel, num_warmup=num_warmup, num_samples=num_samples, progress_bar=False)
    mcmc.run(jax.random.PRNGKey(seed), jnp.asarray(Xs), jnp.asarray(t, dtype=float),
             y=jnp.asarray(y, dtype=float))

    s = mcmc.get_samples()
    tau0 = np.asarray(s["tau0"])                                   # (S,)
    gamma = np.asarray(s["gamma"]) * np.asarray(s["sigma_gamma"])[:, None]  # (S, p)
    tau_draws = tau0[:, None] + gamma @ Xs.T                       # (S, n)

    return {
        "tau_draws": tau_draws,
        "mean": tau_draws.mean(axis=0),
        "sd": tau_draws.std(axis=0),
        "sigma_gamma": np.asarray(s["sigma_gamma"]),
    }


def compare(n: int = 250, seed: int = 0, het: float = 0.9) -> pd.DataFrame:
    """Laplace vs NUTS on one dataset, per-customer.

    The number that matters is the ratio of posterior widths. If Laplace is
    systematically narrower, its intervals under-cover and the abstention rule built
    on them is over-confident -- which would flatter this phase's own claim.
    """
    from keel.models.uplift import HierarchicalCATE

    r = np.random.default_rng(seed)
    X = pd.DataFrame(r.normal(size=(n, 4)), columns=[f"x{i}" for i in range(4)])
    t = r.integers(0, 2, n)
    tau = -0.8 + het * X["x0"].to_numpy()
    eta = -0.5 + 0.6 * X["x1"].to_numpy() + t * tau
    y = (r.random(n) < 1.0 / (1.0 + np.exp(-eta))).astype(int)

    lap = HierarchicalCATE().fit(X, t, y).posterior(X)
    nuts = nuts_posterior(X, t, y, seed=seed)

    return pd.DataFrame({
        "true_tau": tau,
        "laplace_mean": lap.mean,
        "laplace_sd": lap.sd,
        "nuts_mean": nuts["mean"],
        "nuts_sd": nuts["sd"],
        "sd_ratio": lap.sd / np.maximum(nuts["sd"], 1e-12),
    })


if __name__ == "__main__":
    for n in (250, 500, 2000):
        df = compare(n=n, seed=1)
        z_lap = (df.laplace_mean - df.true_tau) / df.laplace_sd
        z_nuts = (df.nuts_mean - df.true_tau) / df.nuts_sd
        print(
            f"n={n:>5}  sd ratio (laplace/nuts) mean={df.sd_ratio.mean():.3f}  "
            f"| z sd: laplace={z_lap.std():.3f} nuts={z_nuts.std():.3f}  "
            f"| mean corr={np.corrcoef(df.laplace_mean, df.nuts_mean)[0,1]:.4f}"
        )
