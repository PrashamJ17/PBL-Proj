"""Hierarchical Bayesian CATE with a usable posterior.

This is the estimator Section 8 of the paper specifies, and the reason the rest of the
project exists. Everything before it establishes a problem: at the sample sizes small
businesses actually have, a point estimate of the treatment effect is unreliable
(D-023: the best conventional method beats random on only 75% of draws at n=500), and
a practitioner cannot tell in advance which correlation regime they are in (D-026).

Neither is solved by a better point estimate. Both are solved by knowing *how uncertain
the estimate is* and declining to act when the uncertainty is wide relative to the
stakes. That requires a posterior, not a number.

The model
---------
A Bayesian logistic regression with a treatment interaction::

    logit P(y_i = 1) = alpha + x_i'beta  +  T_i (tau_0 + x_i'gamma)

so the conditional average treatment effect on the log-odds scale is

    tau(x_i) = tau_0 + x_i'gamma

`alpha, beta` are nuisance: they describe who responds anyway. `tau_0` is the average
effect and `gamma` is its heterogeneity, and the split matters because **their
identifiability is wildly different**. The sign of `tau_0` is usually well determined by
a few hundred subjects. `gamma` almost never is.

Why the shrinkage prior is the whole mechanism
-----------------------------------------------
`gamma ~ Normal(0, sigma_gamma^2)` with `sigma_gamma` **estimated from the data** rather
than fixed. When heterogeneity is not identifiable -- which is the normal situation at
n = 500 -- the marginal likelihood drives `sigma_gamma` toward zero, every `tau_i`
collapses onto `tau_0`, and the model gracefully degrades into "estimate one average
effect well" instead of "estimate 500 individual effects badly".

That degradation is the point. A T-learner cannot do it: it fits two separate models and
differences them, so its per-customer estimates stay noisy no matter how little signal
there is, and the noise is what a top-k rule then ranks on.

Why Laplace rather than MCMC
-----------------------------
`tau_i` is **linear** in the parameters, so under a Gaussian posterior on the
coefficients its own posterior is exactly Gaussian -- mean and variance in closed form,
no sampling, no Monte Carlo error in the decision rule. The Laplace approximation is an
approximation of the *coefficient* posterior, not of anything downstream of it.

It keeps the estimator on numpy and scipy, so the Phase 4 gate runs in CI rather than
on someone's laptop. The approximation is not assumed to be adequate: `tests/` checks
posterior interval coverage against known ground truth, and
`keel.models.uplift.mcmc_check` validates it against NUTS.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import optimize, stats


def _expit(z: np.ndarray) -> np.ndarray:
    """Logistic function, stable at both tails."""
    out = np.empty_like(z, dtype=float)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


@dataclass
class CATEPosterior:
    """Per-customer posterior over the treatment effect.

    A **mixture** of Gaussians, one component per value of `sigma_gamma` on the grid,
    weighted by that value's marginal likelihood. Empirical Bayes -- plugging in a
    single `sigma_gamma_hat` -- ignores uncertainty in the pooling strength itself and
    produces intervals that are too narrow exactly where it matters: small n with real
    heterogeneity. Measured before this change, 90% intervals covered 83%.

    That error runs in the dangerous direction. An over-confident posterior abstains
    *less* than it should, which would flatter the very claim this phase exists to
    test.

    Still closed form. `tau_i` is linear in the coefficients, so each component is
    exactly Gaussian; mixture moments and mixture tail probabilities are both exact
    sums. Nothing here is sampled.
    """

    means: np.ndarray
    """Component means, shape `(n, K)`."""
    sds: np.ndarray
    """Component standard deviations, shape `(n, K)`."""
    weights: np.ndarray
    """Posterior weight of each `sigma_gamma`, shape `(K,)`, summing to 1."""

    @property
    def mean(self) -> np.ndarray:
        """Posterior mean of tau_i on the log-odds scale."""
        return self.means @ self.weights

    @property
    def sd(self) -> np.ndarray:
        """Posterior standard deviation. The quantity this whole phase is about.

        Law of total variance across mixture components: the spread *within* each
        component plus the spread *between* them. The second term is the part
        empirical Bayes throws away.
        """
        m = self.mean[:, None]
        second = ((self.sds**2 + self.means**2) @ self.weights)
        return np.sqrt(np.maximum(second - m[:, 0] ** 2, 0.0))

    def prob_below(self, threshold: np.ndarray | float = 0.0) -> np.ndarray:
        """P(tau_i < threshold), exact for the mixture."""
        thr = np.broadcast_to(np.asarray(threshold, dtype=float), self.mean.shape)
        comp = stats.norm.cdf(
            thr[:, None], loc=self.means, scale=np.maximum(self.sds, 1e-12)
        )
        return comp @ self.weights

    def interval(self, level: float = 0.90) -> tuple[np.ndarray, np.ndarray]:
        """Equal-tailed credible interval.

        Solved on the mixture CDF by bisection rather than using the Gaussian
        quantile of the mixture moments -- the mixture is not Gaussian, and the
        difference is largest in precisely the small-n case that matters.
        """
        lo_q, hi_q = (1.0 - level) / 2.0, 0.5 + level / 2.0
        return self._quantile(lo_q), self._quantile(hi_q)

    def _quantile(self, q: float, iters: int = 60) -> np.ndarray:
        m, s = self.mean, self.sd
        lo, hi = m - 12.0 * s - 1e-6, m + 12.0 * s + 1e-6
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            go_up = self.prob_below(mid) < q
            lo = np.where(go_up, mid, lo)
            hi = np.where(go_up, hi, mid)
        return 0.5 * (lo + hi)

    def prob_beneficial(self) -> np.ndarray:
        """P(tau_i < 0) -- the treatment reduces the outcome.

        Sign convention follows D-013: for churn a *negative* effect is the good one.
        """
        return self.prob_below(0.0)

    def __len__(self) -> int:
        return self.means.shape[0]


class HierarchicalCATE:
    """Bayesian logistic CATE with an adaptively-pooled heterogeneity prior.

    Parameters
    ----------
    prior_sd_beta:
        Prior scale on the baseline covariate effects. Weak; these are nuisance.
    prior_sd_tau0:
        Prior scale on the average treatment effect. Deliberately weak so the data
        determines it -- this is the parameter that *is* identifiable at small n.
    sigma_gamma:
        Prior scale on effect heterogeneity. ``None`` estimates it from the data by
        maximising the Laplace-approximate marginal likelihood (empirical Bayes),
        which is what makes the pooling adaptive rather than assumed. Pass a float
        to fix it, which the tests use to probe the mechanism directly.
    tenant_prior:
        ``(mean, sd)`` for `tau_0`, from a population of other firms. This is the
        cross-tenant pooling of D-041: a new tenant with 300 customers starts from
        what similar firms established rather than from ignorance. ``None`` uses the
        weak default.
    """

    def __init__(
        self,
        prior_sd_beta: float = 1.0,
        prior_sd_tau0: float = 2.5,
        sigma_gamma: float | None = None,
        tenant_prior: tuple[float, float] | None = None,
        max_iter: int = 200,
    ):
        self.prior_sd_beta = prior_sd_beta
        self.prior_sd_tau0 = prior_sd_tau0
        self.sigma_gamma = sigma_gamma
        self.tenant_prior = tenant_prior
        self.max_iter = max_iter

        self.theta_: np.ndarray | None = None
        self.cov_: np.ndarray | None = None
        self.sigma_gamma_: float | None = None
        """The pooling strength actually used. Small means the data did not support
        heterogeneity and every tau_i was shrunk toward the average effect."""
        self.sigma_grid_: np.ndarray | None = None
        self.sigma_weights_: np.ndarray | None = None
        self.components_: list[tuple[np.ndarray, np.ndarray]] = []
        self._mu: np.ndarray | None = None
        self._sd: np.ndarray | None = None
        self.n_features_: int = 0

    # --- design ---------------------------------------------------------------

    def _standardise(self, X: pd.DataFrame | np.ndarray, fit: bool = False) -> np.ndarray:
        A = np.asarray(X, dtype=float)
        if fit:
            self._mu = A.mean(axis=0)
            self._sd = np.maximum(A.std(axis=0), 1e-9)
        return (A - self._mu) / self._sd

    def _design(self, Xs: np.ndarray, t: np.ndarray) -> np.ndarray:
        """`[1, x, T, T*x]` -- the last two blocks carry the treatment effect."""
        n, p = Xs.shape
        t = np.asarray(t, dtype=float).reshape(n, 1)
        return np.hstack([np.ones((n, 1)), Xs, t, t * Xs])

    def _prior_precision(self, p: int, sigma_gamma: float) -> tuple[np.ndarray, np.ndarray]:
        """Diagonal prior precision, and the prior mean it is centred on.

        Only `tau_0` has a non-zero prior mean, and only when a tenant prior is
        supplied -- that is where cross-firm pooling enters.
        """
        tau0_mean, tau0_sd = self.tenant_prior or (0.0, self.prior_sd_tau0)
        sds = np.concatenate([
            [10.0],                             # intercept: essentially flat
            np.full(p, self.prior_sd_beta),     # baseline covariate effects
            [tau0_sd],                          # average treatment effect
            np.full(p, sigma_gamma),            # heterogeneity -- the shrunk block
        ])
        mean = np.zeros(2 * p + 2)
        mean[p + 1] = tau0_mean
        return 1.0 / sds**2, mean

    # --- fitting --------------------------------------------------------------

    def _neg_log_post(self, theta, Z, y, prec, prior_mean):
        eta = Z @ theta
        # log-sum-exp form of the Bernoulli log-likelihood, stable at both tails.
        ll = np.sum(y * eta - np.logaddexp(0.0, eta))
        d = theta - prior_mean
        lp = -0.5 * np.sum(prec * d * d)
        return -(ll + lp)

    def _grad(self, theta, Z, y, prec, prior_mean):
        p = _expit(Z @ theta)
        return -(Z.T @ (y - p) - prec * (theta - prior_mean))

    def _fit_given_sigma(self, Z, y, p_feat, sigma_gamma):
        prec, prior_mean = self._prior_precision(p_feat, sigma_gamma)
        theta0 = np.zeros(Z.shape[1])
        res = optimize.minimize(
            self._neg_log_post, theta0, args=(Z, y, prec, prior_mean),
            jac=self._grad, method="L-BFGS-B",
            options={"maxiter": self.max_iter},
        )
        theta = res.x
        # Laplace: posterior precision is the Hessian of the negative log posterior.
        pr = _expit(Z @ theta)
        W = pr * (1.0 - pr)
        H = Z.T @ (Z * W[:, None]) + np.diag(prec)
        cov = np.linalg.inv(H + 1e-9 * np.eye(H.shape[0]))
        return theta, cov, H, prec, prior_mean

    def _log_marginal(self, Z, y, p_feat, sigma_gamma):
        """Laplace approximation to log p(y | sigma_gamma)."""
        theta, _, H, prec, prior_mean = self._fit_given_sigma(Z, y, p_feat, sigma_gamma)
        return self._log_marginal_from(Z, y, theta, H, prec, prior_mean)

    def _log_marginal_from(self, Z, y, theta, H, prec, prior_mean):
        """The same quantity, from a fit already computed.

        Weighting the grid by this -- rather than taking its argmax -- is what turns
        empirical Bayes into an approximate marginalisation over the pooling strength.
        """
        eta = Z @ theta
        ll = np.sum(y * eta - np.logaddexp(0.0, eta))
        d = theta - prior_mean
        lp = 0.5 * np.sum(np.log(prec)) - 0.5 * np.sum(prec * d * d)
        sign, logdet = np.linalg.slogdet(H)
        if sign <= 0:
            return -np.inf
        return ll + lp - 0.5 * logdet

    def fit(self, X, t, y) -> HierarchicalCATE:
        Xs = self._standardise(X, fit=True)
        y = np.asarray(y, dtype=float)
        t = np.asarray(t, dtype=float)
        Z = self._design(Xs, t)
        self.n_features_ = Xs.shape[1]

        # Same discipline as the survival models (D-051): say what is wrong with the
        # data, not what an optimiser found inconvenient. Each of these is a real
        # situation -- a pilot too small to have produced both outcomes, or one that
        # was never randomised.
        if len(np.unique(y)) < 2:
            raise ValueError(
                f"outcome is constant ({int(y.sum())} positives in {len(y)} rows); "
                "no treatment effect is identifiable from it."
            )
        if len(np.unique(t)) < 2:
            raise ValueError(
                "every subject has the same treatment status; a treatment effect "
                "needs both arms. This usually means the pilot was not randomised."
            )

        # A grid rather than an optimiser, because the fits are then reusable as
        # mixture components. The marginal likelihood is also very flat near zero --
        # exactly the regime that matters -- where a gradient method wanders.
        grid = (
            np.logspace(-3, 0.5, 15) if self.sigma_gamma is None
            else np.array([float(self.sigma_gamma)])
        )

        fits, logmls = [], []
        for s in grid:
            theta, cov, H, prec, prior_mean = self._fit_given_sigma(
                Z, y, self.n_features_, s
            )
            fits.append((theta, cov))
            logmls.append(self._log_marginal_from(Z, y, theta, H, prec, prior_mean))

        logmls = np.asarray(logmls)
        if not np.isfinite(logmls).any():
            raise RuntimeError("no usable sigma_gamma: every marginal likelihood diverged")
        logmls = np.where(np.isfinite(logmls), logmls, -np.inf)

        # Keeping the whole posterior over sigma_gamma, rather than its mode, is what
        # carries pooling-strength uncertainty into every tau_i. Plugging in the mode
        # produced 90% intervals covering 83% at n=250 -- over-confident, in the
        # direction that would have flattered this phase's own claim.
        w = np.exp(logmls - logmls.max())
        w /= w.sum()

        self.sigma_grid_ = grid
        self.sigma_weights_ = w
        self.components_ = fits
        # Reported for interpretation only; nothing downstream uses the point value.
        self.sigma_gamma_ = float(grid[int(np.argmax(logmls))])
        self.theta_ = sum(wk * th for wk, (th, _) in zip(w, fits, strict=True))
        self.cov_ = fits[int(np.argmax(logmls))][1]
        return self

    # --- the posterior --------------------------------------------------------

    def posterior(self, X) -> CATEPosterior:
        """Posterior over tau_i for each row of `X`.

        `tau_i = [1, x_i] . (tau_0, gamma)`, so each mixture component's mean is a
        linear map of that component's coefficient mean, and its variance the
        corresponding quadratic form. Exact given each Gaussian component; the mixing
        over `sigma_gamma` is what carries pooling-strength uncertainty through.
        """
        if self.theta_ is None:
            raise RuntimeError("fit() first")
        # Checked before standardising: the stored mean/sd have the training width,
        # so a mismatch would otherwise surface as a numpy broadcast error naming
        # shapes rather than the actual problem.
        p_in = np.asarray(X).shape[1]
        if p_in != self.n_features_:
            raise ValueError(
                f"expected {self.n_features_} features, got {p_in}. The columns must "
                "match those seen during fit, in the same order."
            )
        Xs = self._standardise(X)
        n, p = Xs.shape

        Zt = np.hstack([np.ones((n, 1)), Xs])       # picks out (tau_0, gamma)
        idx = np.arange(p + 1, 2 * p + 2)

        means = np.empty((n, len(self.components_)))
        sds = np.empty_like(means)
        for k, (theta, cov) in enumerate(self.components_):
            means[:, k] = Zt @ theta[idx]
            cov_tau = cov[np.ix_(idx, idx)]
            var = np.einsum("ij,jk,ik->i", Zt, cov_tau, Zt)
            sds[:, k] = np.sqrt(np.maximum(var, 0.0))

        return CATEPosterior(means=means, sds=sds, weights=self.sigma_weights_)

    def cate(self, X) -> np.ndarray:
        """Point estimate, for comparison against methods that only offer one."""
        return self.posterior(X).mean

    def standardised_features(self, X) -> np.ndarray:
        """`X` on the scale the coefficients act on, so callers can say whether a
        customer is above or below typical without re-deriving the training moments."""
        if self.theta_ is None:
            raise RuntimeError("fit() first")
        return self._standardise(X)

    def effect_contributions(self, X) -> np.ndarray:
        """Exact per-feature contribution to `tau_i`, shape `(n, p)`.

        `tau_i = tau_0 + x_i'gamma` is **linear**, and for a linear model the Shapley
        value of feature `j` is exactly `gamma_j (x_ij - E[x_j])`. Features are
        standardised here, so `E[x_j] = 0` and the contribution is `gamma_j * xs_ij` --
        no sampling, no background dataset, no approximation, and no dependency on a
        SHAP implementation (invariant 7 keeps the core on numpy/scipy).

        Rows sum to `tau_i - tau_0`: what makes this customer differ from the average
        customer. The intercept `tau_0` is deliberately excluded, because "the offer
        works on people in general" is not a reason to treat *this* person.

        Uses the mixture-averaged coefficients, which reproduce the posterior mean of
        `tau_i` exactly -- again because `tau_i` is linear, so averaging the
        coefficients and averaging the predictions are the same operation.
        """
        if self.theta_ is None:
            raise RuntimeError("fit() first")
        p_in = np.asarray(X).shape[1]
        if p_in != self.n_features_:
            raise ValueError(
                f"expected {self.n_features_} features, got {p_in}. The columns must "
                "match those seen during fit, in the same order."
            )
        Xs = self._standardise(X)
        p = self.n_features_
        gamma = self.theta_[p + 2 : 2 * p + 2]
        return Xs * gamma

    def joint_samples(
        self, X, n_samples: int = 500, seed: int | None = 0
    ) -> tuple[np.ndarray, np.ndarray]:
        """Draw `(baseline_logit, tau)` jointly, each of shape `(n, n_samples)`.

        `posterior()` returns the marginal over `tau_i`, which is all a rule that
        thresholds `tau` needs. Converting `tau` to *money* needs more than that: the
        effect on the probability scale is

            delta_p_i = expit(eta0_i + tau_i) - expit(eta0_i)

        which depends on the baseline `eta0_i = alpha + x_i'beta` as well. The two are
        estimated from the same data and are correlated -- a fit that puts a customer's
        baseline risk high tends to put the treatment coefficient low -- so drawing them
        independently would misstate the spread of `delta_p`. They are drawn from the
        same parameter vector here.

        Sampling rather than a closed form because `expit` is nonlinear: the exact
        Gaussian algebra that `AbstentionPolicy` relies on does not survive the
        conversion (D-057).
        """
        if self.theta_ is None:
            raise RuntimeError("fit() first")
        if n_samples < 1:
            raise ValueError(f"n_samples must be >= 1, got {n_samples}")
        p_in = np.asarray(X).shape[1]
        if p_in != self.n_features_:
            raise ValueError(
                f"expected {self.n_features_} features, got {p_in}. The columns must "
                "match those seen during fit, in the same order."
            )

        rng = np.random.default_rng(seed)
        Xs = self._standardise(X)
        n, p = Xs.shape
        Zt = np.hstack([np.ones((n, 1)), Xs])        # (n, p+1)

        # Draw the mixture component first, then the coefficients within it, so that
        # uncertainty about the pooling strength propagates the same way it does in
        # `posterior()`.
        ks = rng.choice(len(self.components_), size=n_samples, p=self.sigma_weights_)
        draws = np.empty((n_samples, 2 * p + 2))
        for k in np.unique(ks):
            rows = ks == k
            theta, cov = self.components_[k]
            # Cholesky with jitter: `cov` is a numerically-inverted Hessian and can
            # lose positive-definiteness in the last bits.
            sym = 0.5 * (cov + cov.T)
            jitter = 1e-10 * max(np.trace(sym) / len(sym), 1.0)
            for _ in range(6):
                try:
                    L = np.linalg.cholesky(sym + jitter * np.eye(len(sym)))
                    break
                except np.linalg.LinAlgError:
                    jitter *= 100
            else:
                raise RuntimeError(
                    "posterior covariance is not positive-definite even with jitter; "
                    "the fit did not converge and its uncertainty cannot be trusted."
                )
            z = rng.standard_normal((int(rows.sum()), len(sym)))
            draws[rows] = theta + z @ L.T

        eta0 = Zt @ draws[:, : p + 1].T               # (n, n_samples)
        tau = Zt @ draws[:, p + 1 :].T
        return eta0, tau


def pool_across_tenants(
    fits: list[HierarchicalCATE], shrink: float = 1.0
) -> tuple[float, float]:
    """Population prior on `tau_0` from firms already fitted.

    The cross-tenant mechanism of D-041, and the project's defensibility claim: a new
    tenant with 300 customers begins from what similar firms established rather than
    from ignorance.

    Returns `(mean, sd)` for use as `tenant_prior`. The spread deliberately combines
    the between-firm variation with each firm's own uncertainty -- treating noisy
    per-firm estimates as if they were known would understate the prior width and make
    a new tenant over-confident, which is the failure this whole phase exists to avoid.
    """
    if not fits:
        raise ValueError("no fitted tenants to pool from")
    means, variances = [], []
    for f in fits:
        if f.theta_ is None:
            raise RuntimeError("every tenant must be fitted before pooling")
        i = f.n_features_ + 1
        means.append(f.theta_[i])
        variances.append(f.cov_[i, i])

    means = np.asarray(means)
    within = float(np.mean(variances))
    between = float(np.var(means, ddof=1)) if len(means) > 1 else 0.0
    return float(np.mean(means)), float(np.sqrt(max(between + within, 1e-6)) * shrink)
