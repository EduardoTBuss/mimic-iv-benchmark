"""Ordinal logistic regression (proportional-odds / cumulative-logit model), from scratch.

Model
-----
For ordered classes c_1 < ... < c_K and features x (p,):

    P(y <= c_k | x) = sigma(theta_k - x^T w),   k = 1..K-1

with strictly increasing thresholds enforced by the reparametrisation

    theta_1 = b_1,   theta_k = theta_{k-1} + exp(d_k)   (k = 2..K-1).

There is no separate intercept: the thresholds play that role. The optimisation vector is
``params = [w (p), b_1, d_2..d_{K-1}]`` (length p + K - 1).

Objective (L2 on ``w`` only, never on the thresholds):

    L = -sum_i s_i log P(y_i | x_i) / sum_i s_i + 0.5 * alpha * ||w||^2

Numerics
--------
With a = theta_y - eta and b = theta_{y-1} - eta (theta_0 = -inf, theta_K = +inf):

    sigma(a) - sigma(b) = sigma(a) * sigma(-b) * (1 - exp(b - a))
    log P = log_expit(a) + log_expit(-b) + log(-expm1(-(a - b)))

and a - b = theta_y - theta_{y-1} = exp(d_y) does not depend on x, so the last term is a
per-class constant. The end classes are the same formula with infinite thresholds
(log_expit(+inf) = 0, expm1(-inf) = -1), so no branch on the class is needed.

Gradient (derivation in ``ordinal_loss_and_grad``):

    dlogP/da = sigma(-a) + r_y,   dlogP/db = -sigma(b) - r_y,   r_y = 1 / expm1(theta_y - theta_{y-1})

Cost per objective evaluation: O(n p) (one mat-vec X w and one X^T v) + O(n) elementwise.
"""

from __future__ import annotations

import warnings
from numbers import Integral, Real

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, log_expit, logit
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.exceptions import ConvergenceWarning
from sklearn.utils._param_validation import Interval
from sklearn.utils.multiclass import check_classification_targets
from sklearn.utils.validation import check_is_fitted, validate_data

__all__ = [
    "OrdinalLogisticRegression",
    "ordinal_loss_and_grad",
    "params_to_thresholds",
    "thresholds_to_params",
]


# ---------------------------------------------------------------------------
# Pure numerical core (module-level so it can be gradient-checked directly)
# ---------------------------------------------------------------------------
def params_to_thresholds(raw: np.ndarray) -> np.ndarray:
    """Map unconstrained ``[b_1, d_2..d_{K-1}]`` (K-1,) to strictly increasing thresholds (K-1,)."""
    raw = np.asarray(raw, dtype=np.float64)
    steps = np.concatenate([raw[:1], np.exp(raw[1:])])
    return np.cumsum(steps)


def thresholds_to_params(theta: np.ndarray) -> np.ndarray:
    """Inverse of :func:`params_to_thresholds`; ``theta`` (K-1,) must be strictly increasing."""
    theta = np.asarray(theta, dtype=np.float64)
    gaps = np.diff(theta)
    if np.any(gaps <= 0):
        raise ValueError("thresholds must be strictly increasing")
    return np.concatenate([theta[:1], np.log(gaps)])


def _extended_thresholds(theta: np.ndarray) -> np.ndarray:
    """(K-1,) -> (K+1,) with -inf / +inf sentinels: class k lives in (ext[k], ext[k+1]]."""
    return np.concatenate([[-np.inf], theta, [np.inf]])


def _log_gap_terms(theta_ext: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-class constants from the threshold gaps g_k = ext[k+1] - ext[k] > 0 (K,).

    Returns ``log(1 - exp(-g_k))`` and ``r_k = 1 / expm1(g_k)``; both are 0 for the end classes
    (g = +inf).
    """
    with np.errstate(divide="ignore", over="ignore"):
        gaps = np.diff(theta_ext)  # (K,), inf at both ends
        log_gap = np.log(-np.expm1(-gaps))
        r = 1.0 / np.expm1(gaps)
    return log_gap, r


def _class_log_proba(eta: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """log P(y = c_k | eta) for every class; eta (n,), theta (K-1,) -> (n, K)."""
    ext = _extended_thresholds(theta)
    log_gap, _ = _log_gap_terms(ext)
    upper = ext[1:][None, :] - eta[:, None]  # a, (n, K)
    lower = ext[:-1][None, :] - eta[:, None]  # b, (n, K)
    return log_expit(upper) + log_expit(-lower) + log_gap[None, :]


def ordinal_loss_and_grad(
    params: np.ndarray,
    X: np.ndarray,
    y_codes: np.ndarray,
    weights: np.ndarray,
    alpha: float,
    n_classes: int,
) -> tuple[float, np.ndarray]:
    """Penalised mean negative log-likelihood and its exact gradient.

    Parameters
    ----------
    params : (p + K - 1,) ``[w, b_1, d_2..d_{K-1}]``.
    X : (n, p) float64 design matrix.
    y_codes : (n,) int class codes in ``0..K-1`` (0 = lowest class).
    weights : (n,) non-negative sample weights, **already normalised to sum to 1**.
    alpha : L2 strength on ``w`` only.
    n_classes : K >= 2.

    Gradient derivation (l_i = log P_i, a_i = theta_{y_i} - eta_i, b_i = theta_{y_i - 1} - eta_i):
        l = log_expit(a) + log_expit(-b) + log(1 - exp(b - a))
        dl/da = sigma(-a) + 1/expm1(a - b) =: ga,   dl/db = -sigma(b) - 1/expm1(a - b) =: gb
        dl/deta = -(ga + gb)                       => dL/dw = X^T (s * (ga + gb)) + alpha w
        dL/dtheta_j = -[sum_{y_i = j} s_i ga_i + sum_{y_i = j + 1} s_i gb_i]   (bincount)
        theta_j = b_1 + sum_{m <= j} exp(d_m)      => dL/db_1 = sum_j dL/dtheta_j,
                                                     dL/dd_m = exp(d_m) sum_{j >= m} dL/dtheta_j
    """
    p = X.shape[1]
    K = n_classes
    w = params[:p]
    raw = params[p:]
    theta = params_to_thresholds(raw)
    ext = _extended_thresholds(theta)
    log_gap, r = _log_gap_terms(ext)

    eta = X @ w  # (n,)
    a = ext[y_codes + 1] - eta  # upper, +inf for the top class
    b = ext[y_codes] - eta  # lower, -inf for the bottom class

    loglik = log_expit(a) + log_expit(-b) + log_gap[y_codes]
    loss = -float(np.dot(weights, loglik)) + 0.5 * alpha * float(np.dot(w, w))

    r_i = r[y_codes]
    ga = expit(-a) + r_i  # 0 for the top class (sigma(-inf) = 0, r = 0)
    gb = -expit(b) - r_i  # 0 for the bottom class

    grad_w = X.T @ (weights * (ga + gb)) + alpha * w

    # dL/dtheta_j for j = 0..K-2 (0-indexed threshold between class j and j+1):
    # theta_j is the upper bound of class j and the lower bound of class j+1.
    up = np.bincount(y_codes, weights=weights * ga, minlength=K)  # (K,)
    lo = np.bincount(y_codes, weights=weights * gb, minlength=K)  # (K,)
    grad_theta = -(up[: K - 1] + lo[1:K])  # (K-1,)

    # Chain rule through the cumulative-exp reparametrisation.
    tail = np.cumsum(grad_theta[::-1])[::-1]  # sum_{j >= m} dL/dtheta_j
    grad_raw = np.empty_like(raw)
    grad_raw[0] = tail[0]
    grad_raw[1:] = np.exp(raw[1:]) * tail[1:]

    return loss, np.concatenate([grad_w, grad_raw])


# ---------------------------------------------------------------------------
# scikit-learn estimator
# ---------------------------------------------------------------------------
class OrdinalLogisticRegression(ClassifierMixin, BaseEstimator):
    """Proportional-odds (cumulative-logit) ordinal logistic regression.

    ``P(y <= c_k | x) = sigma(theta_k - x^T w)``, thresholds strictly increasing by construction.
    Larger ``x^T w`` shifts mass toward *higher* classes. Class order is the sort order of the
    labels (``np.unique``), so any orderable labels work (ints, floats, strings in lexicographic
    order).

    Parameters
    ----------
    alpha : float, default=1e-4
        L2 penalty ``0.5 * alpha * ||w||^2`` on the coefficients only (thresholds unpenalised).
    max_iter : int, default=500
        Maximum L-BFGS-B iterations.
    tol : float, default=1e-6
        L-BFGS-B ``gtol`` (max abs projected gradient); ``ftol`` is set to ``1e-3 * tol``.
    classes : array-like or None, default=None
        Optional full ordered label set. When given, ``fit`` raises ``ValueError`` if any of these
        classes is absent from the training labels (e.g. a rare level lost in a CV fold or after
        undersampling), and rejects unknown labels. When None, the classes are those seen in ``y``.

    Attributes
    ----------
    classes_ : (K,) ordered labels.
    coef_ : (p,) coefficients ``w``.
    thresholds_ : (K-1,) strictly increasing cut-points ``theta``.
    n_features_in_ : int.
    n_iter_ : int, L-BFGS-B iterations used.
    converged_ : bool, optimizer success flag.
    loss_ : float, final value of the objective.
    """

    _parameter_constraints: dict = {
        "alpha": [Interval(Real, 0, None, closed="left")],
        "max_iter": [Interval(Integral, 1, None, closed="left")],
        "tol": [Interval(Real, 0, None, closed="neither")],
        "classes": ["array-like", None],
    }

    def __init__(self, alpha: float = 1e-4, max_iter: int = 500, tol: float = 1e-6, classes=None):
        self.alpha = alpha
        self.max_iter = max_iter
        self.tol = tol
        self.classes = classes

    # -- fitting -------------------------------------------------------------
    def fit(self, X, y, sample_weight=None):
        """Fit by L-BFGS-B on the penalised weighted mean NLL.

        X : (n, p) numeric; y : (n,) orderable labels; sample_weight : (n,) >= 0 or None.
        """
        self._validate_params()
        X, y = validate_data(self, X, y, dtype=np.float64, order="C", y_numeric=False)
        check_classification_targets(y)
        n = X.shape[0]

        seen = np.unique(y)
        if self.classes is not None:
            classes = np.unique(np.asarray(self.classes))
            unknown = np.setdiff1d(seen, classes)
            if unknown.size:
                raise ValueError(f"y contains labels not in `classes`: {unknown.tolist()}")
            missing = np.setdiff1d(classes, seen)
            if missing.size:
                raise ValueError(
                    f"class(es) {missing.tolist()} absent from the training labels; the "
                    "proportional-odds thresholds for an unseen class are not identifiable."
                )
        else:
            classes = seen
        if classes.size < 2:
            raise ValueError(f"need at least 2 classes to fit, got {classes.size} class(es): {classes.tolist()}")
        y_codes = np.searchsorted(classes, y).astype(np.intp)
        K = classes.size

        if sample_weight is None:
            sw = np.ones(n, dtype=np.float64)
        else:
            sw = np.asarray(sample_weight, dtype=np.float64).reshape(-1)
            if sw.shape[0] != n:
                raise ValueError(f"sample_weight has {sw.shape[0]} entries, expected {n}")
            if not np.all(np.isfinite(sw)) or np.any(sw < 0):
                raise ValueError("sample_weight must be finite and non-negative")
        total = sw.sum()
        if total <= 0:
            raise ValueError("sample_weight sums to zero")
        sw = sw / total

        class_mass = np.bincount(y_codes, weights=sw, minlength=K)
        empty = classes[class_mass <= 0]
        if empty.size:
            raise ValueError(
                f"class(es) {empty.tolist()} have zero total sample_weight in the training data; "
                "the model is not identifiable without at least one weighted observation per class."
            )

        # Initialise thresholds from the marginal (weighted) cumulative frequencies, w = 0.
        cum = np.clip(np.cumsum(class_mass)[: K - 1], 1e-12, 1 - 1e-12)
        theta0 = logit(cum)
        # Strictly increasing is guaranteed by positive class mass, but guard rounding ties.
        theta0 = theta0[0] + np.concatenate([[0.0], np.cumsum(np.maximum(np.diff(theta0), 1e-8))])
        x0 = np.concatenate([np.zeros(X.shape[1]), thresholds_to_params(theta0)])

        alpha = float(self.alpha)
        res = minimize(
            ordinal_loss_and_grad,
            x0,
            args=(X, y_codes, sw, alpha, K),
            method="L-BFGS-B",
            jac=True,
            options={"maxiter": int(self.max_iter), "gtol": float(self.tol), "ftol": 1e-3 * float(self.tol)},
        )
        if not np.all(np.isfinite(res.x)):
            raise FloatingPointError("L-BFGS-B returned non-finite parameters")

        p = X.shape[1]
        self.classes_ = classes
        self.coef_ = res.x[:p].copy()
        self.thresholds_ = params_to_thresholds(res.x[p:])
        self.n_iter_ = int(res.nit)
        self.converged_ = bool(res.success)
        self.loss_ = float(res.fun)
        if not self.converged_:
            warnings.warn(
                f"OrdinalLogisticRegression did not converge in {self.max_iter} iterations "
                f"({res.message}); consider standardising X or raising max_iter.",
                ConvergenceWarning,
                stacklevel=2,
            )
        return self

    # -- inference -----------------------------------------------------------
    def decision_function(self, X) -> np.ndarray:
        """Latent score ``x^T w``, shape (n,). Higher = more mass on higher classes.

        Note: this is the ordinal linear predictor, NOT scikit-learn's classifier convention
        (binary: ``> 0`` means ``classes_[1]``; multiclass: shape (n, K)). Use ``predict_proba``
        for scorers/calibration that need per-class scores.
        """
        check_is_fitted(self)
        X = validate_data(self, X, dtype=np.float64, reset=False)
        return X @ self.coef_

    def predict_log_proba(self, X) -> np.ndarray:
        """Stable log P(y = c_k | x), shape (n, K)."""
        return _class_log_proba(self.decision_function(X), self.thresholds_)

    def predict_proba(self, X) -> np.ndarray:
        """P(y = c_k | x), shape (n, K): non-negative, rows sum to 1."""
        proba = np.exp(self.predict_log_proba(X))
        np.clip(proba, 0.0, 1.0, out=proba)
        proba /= proba.sum(axis=1, keepdims=True)
        return proba

    def predict(self, X) -> np.ndarray:
        """Most probable class (mode of the predictive distribution), shape (n,)."""
        log_proba = self.predict_log_proba(X)  # runs check_is_fitted before touching classes_
        return self.classes_[np.argmax(log_proba, axis=1)]
