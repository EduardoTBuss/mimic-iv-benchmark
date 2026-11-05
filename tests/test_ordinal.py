"""Numerical validation of the from-scratch ordinal (proportional-odds) logistic regression.

All data is simulated here from the model itself; nothing touches MIMIC.
"""

from __future__ import annotations

import pickle
import time
import warnings

import numpy as np
import pytest
from scipy.special import expit
from sklearn.base import clone
from sklearn.exceptions import NotFittedError
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from triagebench.models.ordinal import (
    OrdinalLogisticRegression,
    ordinal_loss_and_grad,
    params_to_thresholds,
    thresholds_to_params,
)

W_TRUE = np.array([1.0, -0.6, 0.35, 0.0])
THETA_TRUE = np.array([-2.5, -0.8, 0.6, 2.2])  # K = 5


def simulate(n: int, w: np.ndarray, theta: np.ndarray, seed: int, labels=None):
    """Draw (X, y) from the latent-variable form: z = x^T w + Logistic(0, 1), y = #{theta < z}.

    Then P(y <= k | x) = P(z <= theta_k) = sigma(theta_k - x^T w), i.e. exactly the fitted model.
    """
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, w.size))
    z = X @ w + rng.logistic(size=n)
    codes = np.searchsorted(theta, z)  # 0..K-1
    labels = np.arange(1, theta.size + 2) if labels is None else np.asarray(labels)
    return X, labels[codes]


def numeric_grad(f, x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    g = np.empty_like(x)
    for j in range(x.size):
        e = np.zeros_like(x)
        e[j] = eps
        g[j] = (f(x + e) - f(x - e)) / (2 * eps)
    return g


def naive_loss(params, X, y_codes, weights, alpha, K):
    """Obviously-correct (but unstable in the tails) reference: diff of cumulative sigmoids."""
    p = X.shape[1]
    w, theta = params[:p], params_to_thresholds(params[p:])
    cdf = np.column_stack([np.zeros(len(X)), expit(theta[None, :] - (X @ w)[:, None]), np.ones(len(X))])
    prob = cdf[np.arange(len(X)), y_codes + 1] - cdf[np.arange(len(X)), y_codes]
    return -np.dot(weights, np.log(prob)) + 0.5 * alpha * w @ w


# ---------------------------------------------------------------------------
# 1. Gradient check
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("weighted", [False, True])
@pytest.mark.parametrize("scale", [0.5, 1.5, 4.0])
def test_gradient_matches_central_differences(weighted, scale):
    rng = np.random.default_rng(10 + weighted)
    n, p, K = 400, 5, 5
    X = rng.normal(size=(n, p))
    y = rng.integers(0, K, n)
    s = rng.integers(0, 5, n).astype(float) if weighted else np.ones(n)
    s /= s.sum()
    worst = 0.0
    for _ in range(10):
        params = rng.normal(size=p + K - 1) * scale

        def f(q):
            return ordinal_loss_and_grad(q, X, y, s, 0.7, K)[0]

        g = ordinal_loss_and_grad(params, X, y, s, 0.7, K)[1]
        g_num = numeric_grad(f, params)
        rel = np.max(np.abs(g - g_num)) / max(np.max(np.abs(g)), np.max(np.abs(g_num)), 1e-8)
        worst = max(worst, rel)
    print(f"\n[gradcheck weighted={weighted} scale={scale}] max rel err = {worst:.2e}")
    assert worst < 1e-5


def test_gradient_check_two_classes_and_tiny_gaps():
    """K = 2 (no middle class) and nearly-tied thresholds (d very negative -> r_k large)."""
    rng = np.random.default_rng(3)
    X = rng.normal(size=(300, 3))
    for K, raw in [(2, np.array([0.3])), (4, np.array([0.1, -6.0, -4.0]))]:
        y = rng.integers(0, K, 300)
        s = np.full(300, 1 / 300)
        params = np.concatenate([rng.normal(size=3), raw])
        g = ordinal_loss_and_grad(params, X, y, s, 0.2, K)[1]
        g_num = numeric_grad(lambda q, y=y, s=s, K=K: ordinal_loss_and_grad(q, X, y, s, 0.2, K)[0], params, 1e-7)
        rel = np.max(np.abs(g - g_num)) / np.max(np.abs(g))
        assert rel < 1e-5, (K, rel)


def test_loss_matches_naive_reference_and_is_stable_in_tails():
    rng = np.random.default_rng(4)
    n, p, K = 500, 4, 5
    X = rng.normal(size=(n, p))
    y = rng.integers(0, K, n)
    s = np.full(n, 1 / n)
    params = np.concatenate([rng.normal(size=p) * 0.5, thresholds_to_params(THETA_TRUE)])
    f = ordinal_loss_and_grad(params, X, y, s, 0.1, K)[0]
    np.testing.assert_allclose(f, naive_loss(params, X, y, s, 0.1, K), rtol=1e-12)

    # Extreme linear predictor (|eta| ~ 1e2-1e3): the naive form gives log(0) = -inf for the
    # observed classes; the stable form must stay finite with a finite, correct gradient.
    big = params.copy()
    big[:p] *= 400.0
    with np.errstate(divide="ignore"):
        assert not np.isfinite(naive_loss(big, X, y, s, 0.0, K))
    f_big, g_big = ordinal_loss_and_grad(big, X, y, s, 0.0, K)
    assert np.isfinite(f_big) and np.all(np.isfinite(g_big))
    g_num = numeric_grad(lambda q: ordinal_loss_and_grad(q, X, y, s, 0.0, K)[0], big, 1e-5)
    np.testing.assert_allclose(g_big, g_num, rtol=1e-5, atol=1e-6 * np.max(np.abs(g_big)))


def test_threshold_reparametrisation_round_trip():
    theta = np.array([-3.0, -2.999, 0.0, 7.5])
    np.testing.assert_allclose(params_to_thresholds(thresholds_to_params(theta)), theta, atol=1e-12)
    with pytest.raises(ValueError):
        thresholds_to_params(np.array([0.0, 0.0]))


# ---------------------------------------------------------------------------
# 2. Parameter recovery + golden model (statsmodels OrderedModel)
# ---------------------------------------------------------------------------
def test_recovers_true_parameters():
    X, y = simulate(20_000, W_TRUE, THETA_TRUE, seed=0)
    m = OrdinalLogisticRegression().fit(X, y)
    assert m.converged_
    err_w = np.max(np.abs(m.coef_ - W_TRUE))
    err_t = np.max(np.abs(m.thresholds_ - THETA_TRUE))
    print(f"\n[recovery n=20000] max|w_hat-w|={err_w:.4f}  max|theta_hat-theta|={err_t:.4f}  nit={m.n_iter_}")
    assert err_w < 0.1
    assert err_t < 0.15


def test_matches_statsmodels_ordered_logit_mle():
    """Golden model: with alpha = 0 our optimum must equal statsmodels' unpenalised MLE."""
    om = pytest.importorskip("statsmodels.miscmodels.ordinal_model")
    X, y = simulate(3000, W_TRUE[:3], THETA_TRUE[:3], seed=1)
    m = OrdinalLogisticRegression(alpha=0.0, tol=1e-10).fit(X, y)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ref = om.OrderedModel(y, X, distr="logit").fit(method="bfgs", disp=False, maxiter=3000, gtol=1e-10)
    ref_theta = ref.model.transform_threshold_params(ref.params)[1:-1]
    np.testing.assert_allclose(m.coef_, ref.params[:3], atol=1e-5)
    np.testing.assert_allclose(m.thresholds_, ref_theta, atol=1e-5)
    np.testing.assert_allclose(m.loss_, -ref.llf / len(y), rtol=1e-9)


# ---------------------------------------------------------------------------
# 3. Probabilities
# ---------------------------------------------------------------------------
def test_probabilities_are_valid_even_for_extreme_inputs():
    X, y = simulate(3000, W_TRUE, THETA_TRUE, seed=2)
    m = OrdinalLogisticRegression().fit(X, y)
    assert np.all(np.diff(m.thresholds_) > 0)
    rng = np.random.default_rng(5)
    X_test = np.vstack([rng.normal(size=(500, 4)), rng.normal(size=(500, 4)) * 1e3])
    P = m.predict_proba(X_test)
    assert P.shape == (1000, 5)
    assert np.all(np.isfinite(P)) and np.all(P >= 0) and np.all(P <= 1)
    np.testing.assert_allclose(P.sum(axis=1), 1.0, atol=1e-12)
    # cumulative probabilities must equal the model definition sigma(theta_k - eta)
    eta = m.decision_function(X_test[:500])
    np.testing.assert_allclose(np.cumsum(P[:500], axis=1)[:, :-1],
                               expit(m.thresholds_[None, :] - eta[:, None]), atol=1e-12)
    np.testing.assert_allclose(eta, X_test[:500] @ m.coef_)
    np.testing.assert_array_equal(m.predict(X_test), m.classes_[P.argmax(axis=1)])


# ---------------------------------------------------------------------------
# 4. Integer sample_weight == duplicated rows
# ---------------------------------------------------------------------------
def test_integer_sample_weight_equals_row_duplication():
    X, y = simulate(2000, W_TRUE, THETA_TRUE, seed=3)
    sw = np.random.default_rng(6).integers(0, 4, size=len(y))  # includes zeros (= dropped rows)
    a = OrdinalLogisticRegression(alpha=1e-3, tol=1e-10).fit(X, y, sample_weight=sw)
    b = OrdinalLogisticRegression(alpha=1e-3, tol=1e-10).fit(np.repeat(X, sw, axis=0), np.repeat(y, sw))
    np.testing.assert_allclose(a.coef_, b.coef_, atol=1e-6)
    np.testing.assert_allclose(a.thresholds_, b.thresholds_, atol=1e-6)
    np.testing.assert_allclose(a.loss_, b.loss_, rtol=1e-10)
    # weights are normalised: a global rescale must not change anything
    c = OrdinalLogisticRegression(alpha=1e-3, tol=1e-10).fit(X, y, sample_weight=sw * 7.3)
    np.testing.assert_allclose(a.coef_, c.coef_, atol=1e-6)


# ---------------------------------------------------------------------------
# 5. scikit-learn / imbalanced-learn API
# ---------------------------------------------------------------------------
def test_clone_get_set_params_and_pickle():
    m = OrdinalLogisticRegression(alpha=0.01, max_iter=50, tol=1e-5)
    assert m.get_params() == {"alpha": 0.01, "max_iter": 50, "tol": 1e-5, "classes": None}
    c = clone(m)
    assert c is not m and c.get_params() == m.get_params()
    c.set_params(alpha=0.5)
    assert c.alpha == 0.5 and m.alpha == 0.01
    with pytest.raises(NotFittedError):
        m.predict(np.zeros((2, 4)))
    X, y = simulate(1000, W_TRUE, THETA_TRUE, seed=4)
    m.fit(X, y)
    m2 = pickle.loads(pickle.dumps(m))
    np.testing.assert_array_equal(m.predict_proba(X), m2.predict_proba(X))
    with pytest.raises(ValueError):
        m.predict(np.zeros((2, 3)))  # wrong n_features
    with pytest.raises(ValueError):
        OrdinalLogisticRegression(alpha=-1.0).fit(X, y)


def test_inside_sklearn_pipeline_with_scaler():
    X, y = simulate(4000, W_TRUE, THETA_TRUE, seed=5)
    X_raw = X * np.array([10.0, 0.1, 3.0, 1.0]) + np.array([100.0, -5.0, 0.0, 2.0])
    pipe = Pipeline([("scale", StandardScaler()), ("model", OrdinalLogisticRegression())])
    pipe.fit(X_raw, y, model__sample_weight=np.ones(len(y)))
    assert pipe.predict_proba(X_raw).shape == (4000, 5)
    ref = OrdinalLogisticRegression().fit(StandardScaler().fit_transform(X_raw), y)
    np.testing.assert_allclose(pipe.named_steps["model"].coef_, ref.coef_, atol=1e-10)
    majority = np.max(np.unique(y, return_counts=True)[1]) / len(y)
    assert pipe.score(X_raw, y) > majority + 0.05
    np.testing.assert_array_equal(clone(pipe).fit(X_raw, y).predict(X_raw), pipe.predict(X_raw))


def test_inside_imblearn_pipeline_with_sample_weight():
    imb = pytest.importorskip("imblearn.pipeline")
    X, y = simulate(3000, W_TRUE, THETA_TRUE, seed=6)
    sw = np.random.default_rng(7).integers(1, 3, size=len(y)).astype(float)
    pipe = imb.Pipeline([("scale", StandardScaler()), ("model", OrdinalLogisticRegression(tol=1e-10))])
    pipe.fit(X, y, model__sample_weight=sw)
    ref = OrdinalLogisticRegression(tol=1e-10).fit(StandardScaler().fit_transform(X), y, sample_weight=sw)
    np.testing.assert_allclose(pipe.named_steps["model"].coef_, ref.coef_, atol=1e-8)


# ---------------------------------------------------------------------------
# 6. Labels and failure modes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("labels", [[1, 2, 3, 4, 5], [-10, 0, 7, 42, 1000], ["a", "b", "c", "d", "e"]])
def test_arbitrary_orderable_labels_give_identical_fit(labels):
    X, codes = simulate(3000, W_TRUE, THETA_TRUE, seed=7, labels=np.arange(5))
    y = np.asarray(labels)[codes]
    m = OrdinalLogisticRegression().fit(X, y)
    ref = OrdinalLogisticRegression().fit(X, codes)
    np.testing.assert_array_equal(m.classes_, np.asarray(labels))
    np.testing.assert_allclose(m.coef_, ref.coef_, atol=1e-12)
    np.testing.assert_array_equal(m.predict(X), np.asarray(labels)[ref.predict(X)])
    assert set(np.unique(m.predict(X))) <= set(labels)


def test_missing_or_degenerate_classes_raise_clear_errors():
    X, y = simulate(2000, W_TRUE, THETA_TRUE, seed=8)  # labels 1..5
    keep = y != 3
    with pytest.raises(ValueError, match=r"absent from the training labels"):
        OrdinalLogisticRegression(classes=[1, 2, 3, 4, 5]).fit(X[keep], y[keep])
    with pytest.raises(ValueError, match=r"not in `classes`"):
        OrdinalLogisticRegression(classes=[1, 2, 3, 4]).fit(X, y)
    sw = np.where(y == 2, 0.0, 1.0)
    with pytest.raises(ValueError, match=r"zero total sample_weight"):
        OrdinalLogisticRegression().fit(X, y, sample_weight=sw)
    with pytest.raises(ValueError, match=r"at least 2 classes"):
        OrdinalLogisticRegression().fit(X, np.ones(len(y), dtype=int))
    with pytest.raises(ValueError, match=r"non-negative"):
        OrdinalLogisticRegression().fit(X, y, sample_weight=-np.ones(len(y)))
    # Without `classes`, a gap in integer labels is (by design) treated as a 4-class problem.
    m = OrdinalLogisticRegression().fit(X[keep], y[keep])
    assert m.predict_proba(X).shape == (2000, 4)


# ---------------------------------------------------------------------------
# 7. Scale: n = 300 000, p = 15
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_fits_300k_by_15_in_reasonable_time():
    rng = np.random.default_rng(9)
    w = rng.normal(size=15) * 0.4
    X, y = simulate(300_000, w, THETA_TRUE, seed=9)
    m = OrdinalLogisticRegression()
    t0 = time.perf_counter()
    m.fit(X, y)
    fit_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    m.predict_proba(X)
    pred_s = time.perf_counter() - t0
    print(f"\n[scale n=300000 p=15] fit={fit_s:.2f}s nit={m.n_iter_} converged={m.converged_} "
          f"predict_proba={pred_s:.2f}s max|w_hat-w|={np.max(np.abs(m.coef_ - w)):.4f}")
    assert m.converged_
    assert np.max(np.abs(m.coef_ - w)) < 0.03
    assert fit_s < 60.0
