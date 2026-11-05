"""Leakage guards: patient-level partitions, train-only statistics, fit-only resampling,
and no target/ID columns as features. SYNTHETIC data only."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sklearn.base import BaseEstimator, ClassifierMixin

from tests._helpers import FORBIDDEN_FEATURES, make_cfg, make_ctx, prepare
from tests.conftest import REPO
from triagebench.data.split import PARTITIONS, assign_partitions, split_summary
from triagebench.evaluation import protocol
from triagebench.evaluation.protocol import load_task_data, run_task
from triagebench.models import imbalance
from triagebench.models.imbalance import build_pipeline, stratified_subsample
from triagebench.runner.tasks import Task
from triagebench.utils.config import ConfigError, load_config

FRACTIONS = {"train": 0.70, "val": 0.15, "test": 0.15}
SEEDS = (1, 2, 3, 7, 42)


@pytest.fixture(scope="module")
def env(tmp_path_factory, synthetic_zip):
    root = tmp_path_factory.mktemp("leak")
    cfg = make_cfg(root, synthetic_zip)
    _, prepared = prepare(cfg)
    return {"cfg": cfg, "prepared": prepared, "root": root}


@pytest.fixture(scope="module")
def variant_a(env):
    return pd.read_parquet(env["prepared"] / "private" / "A_keep_encode.parquet")


# --------------------------------------------------------------------------- 1. patient-level split

@pytest.mark.parametrize("seed", SEEDS)
def test_no_patient_in_two_partitions_and_every_stay_assigned(variant_a, seed):
    assign = assign_partitions(variant_a, seed, FRACTIONS)
    assert len(assign) == len(variant_a)
    assert assign["stay_id"].is_unique
    assert set(assign["stay_id"]) == set(variant_a["stay_id"])
    assert assign["partition"].notna().all()
    assert set(assign["partition"]) == set(PARTITIONS)
    parts_per_patient = assign.groupby("subject_id")["partition"].nunique()
    assert parts_per_patient.max() == 1
    assert all(v == 0 for v in split_summary(assign, variant_a)["patient_overlap"].values())


@pytest.mark.parametrize("seed", SEEDS)
def test_patient_fractions_close_to_70_15_15(variant_a, seed):
    assign = assign_partitions(variant_a, seed, FRACTIONS)
    patients = assign.drop_duplicates("subject_id")["partition"].value_counts(normalize=True)
    stays = assign["partition"].value_counts(normalize=True)
    for part, frac in FRACTIONS.items():
        # patients are cut exactly (up to per-stratum rounding)
        assert patients[part] == pytest.approx(frac, abs=0.01)
        # stays follow only loosely: the synthetic visit counts are heavy-tailed (Pareto)
        assert stays[part] == pytest.approx(frac, abs=0.10)


@pytest.mark.parametrize("seed", SEEDS)
def test_urgent_strata_spread_over_every_partition(variant_a, seed):
    assign = assign_partitions(variant_a, seed, FRACTIONS)
    pmin = variant_a.groupby("subject_id")["acuity"].min()
    for level in (1, 2, 3):
        ids = pmin.index[pmin == level]
        got = set(assign.loc[assign["subject_id"].isin(ids), "partition"])
        assert got == set(PARTITIONS), f"acuity-{level} patients missing from some partition"


@pytest.mark.parametrize("seed", SEEDS)
def test_split_is_deterministic_and_independent_of_row_order(variant_a, seed):
    a = assign_partitions(variant_a, seed, FRACTIONS).set_index("stay_id")["partition"]
    shuffled = variant_a.sample(frac=1.0, random_state=seed + 1000).reset_index(drop=True)
    b = assign_partitions(shuffled, seed, FRACTIONS).set_index("stay_id")["partition"]
    pd.testing.assert_series_equal(a.sort_index(), b.sort_index())


def test_different_seeds_give_different_partitions(variant_a):
    maps = [assign_partitions(variant_a, s, FRACTIONS).set_index("stay_id")["partition"].sort_index() for s in SEEDS]
    for i in range(len(maps)):
        for j in range(i + 1, len(maps)):
            changed = (maps[i] != maps[j]).mean()
            assert changed > 0.2, f"seeds {SEEDS[i]} and {SEEDS[j]} give nearly the same split ({changed:.2%})"


def test_patient_with_missing_label_is_rejected_not_silently_dropped():
    df = pd.DataFrame({"stay_id": [1, 2, 3], "subject_id": [10, 10, 11], "acuity": [np.nan, np.nan, 3.0]})
    with pytest.raises(RuntimeError, match="not assigned"):
        assign_partitions(df, 1, FRACTIONS)


@settings(max_examples=60, deadline=None)
@given(
    subjects=st.lists(st.integers(1, 40), min_size=1, max_size=120),
    labels=st.lists(st.integers(1, 5), min_size=120, max_size=120),
    seed=st.integers(0, 2**31 - 1),
)
def test_property_group_disjoint_on_random_frames(subjects, labels, seed):
    df = pd.DataFrame({"stay_id": np.arange(len(subjects)) + 1, "subject_id": subjects,
                       "acuity": labels[:len(subjects)]})
    assign = assign_partitions(df, seed, FRACTIONS)
    assert len(assign) == len(df)
    assert assign["partition"].isin(PARTITIONS).all()
    assert assign.groupby("subject_id")["partition"].nunique().max() == 1


def test_prepared_splits_are_nested_across_variants(env):
    """B is a subset of A; C has exactly A's stays; one split file serves all variants."""
    priv = env["prepared"] / "private"
    a = pd.read_parquet(priv / "A_keep_encode.parquet")
    b = pd.read_parquet(priv / "B_pain_numeric_only.parquet")
    c = pd.read_parquet(priv / "C_values_only.parquet")
    assert set(b["stay_id"]) < set(a["stay_id"])
    assert set(c["stay_id"]) == set(a["stay_id"])
    assert (b["pain_kind"] == "numeric").all()
    for seed in env["cfg"]["split"]["seeds"]:
        split = pd.read_parquet(priv / "splits" / f"seed_{seed}.parquet").set_index("stay_id")["partition"]
        assert set(split.index) == set(a["stay_id"])
        assert split.reindex(b["stay_id"]).notna().all()
        # the partition of a stay is the same object whichever variant reads it
        parts_a = load_task_data(make_ctx(env["cfg"], env["prepared"], env["root"]), "A_keep_encode", seed)
        parts_b = load_task_data(make_ctx(env["cfg"], env["prepared"], env["root"]), "B_pain_numeric_only", seed)
        for part in PARTITIONS:
            assert set(parts_b[part]["stay_id"]) <= set(parts_a[part]["stay_id"])
        subj = [set(parts_a[p]["subject_id"]) for p in PARTITIONS]
        assert not (subj[0] & subj[1] or subj[0] & subj[2] or subj[1] & subj[2])


def test_prepared_split_files_equal_a_fresh_assignment(env, variant_a):
    for seed in env["cfg"]["split"]["seeds"]:
        stored = pd.read_parquet(env["prepared"] / "private" / "splits" / f"seed_{seed}.parquet")
        fresh = assign_partitions(variant_a, seed, env["cfg"]["split"]["fractions"])
        pd.testing.assert_frame_equal(stored.sort_values("stay_id").reset_index(drop=True),
                                      fresh.sort_values("stay_id").reset_index(drop=True), check_dtype=False)


# --------------------------------------------------------------------------- 2. train-only statistics

def _parts(env, variant="A_keep_encode", seed=1):
    return load_task_data(make_ctx(env["cfg"], env["prepared"], env["root"]), variant, seed)


def _features(cfg, variant):
    v = cfg["variants"][variant]
    return list(v["numeric_features"]), list(v["categorical_features"])


@pytest.mark.filterwarnings("ignore::sklearn.exceptions.ConvergenceWarning")  # mlp capped at 5 epochs
@pytest.mark.parametrize("model", ["logreg", "knn", "mlp"])  # needs_scaling=True models
def test_imputer_and_scaler_statistics_come_from_train_only(env, model):
    cfg = env["cfg"]
    num, cat = _features(cfg, "A_keep_encode")
    parts = _parts(env)
    X_tr = parts["train"][num + cat]
    # A test partition built to have very different statistics (shifted, extra missingness).
    X_te = parts["test"][num + cat].copy()
    X_te[num] = X_te[num] + 500.0
    y_tr = parts["train"]["acuity"].to_numpy() - 1

    pipe = build_pipeline(model, {}, "none", cfg, cfg["variants"]["A_keep_encode"], seed=0, threads=1)
    if model == "mlp":
        pipe.set_params(model__max_iter=5)
    pipe.fit(X_tr, y_tr)
    num_pipe = pipe.named_steps["pre"].named_transformers_["num"]
    medians = num_pipe.named_steps["impute"].statistics_
    scaler = num_pipe.named_steps["scale"]

    exp_median = np.nanmedian(X_tr[num].to_numpy(dtype=float), axis=0)
    imputed = X_tr[num].to_numpy(dtype=float).copy()
    nan_r, nan_c = np.nonzero(np.isnan(imputed))
    imputed[nan_r, nan_c] = exp_median[nan_c]
    np.testing.assert_allclose(medians, exp_median, rtol=0, atol=1e-12)
    np.testing.assert_allclose(scaler.mean_, imputed.mean(axis=0), rtol=1e-12)
    np.testing.assert_allclose(scaler.scale_, imputed.std(axis=0, ddof=0), rtol=1e-10)

    both = pd.concat([X_tr, X_te])[num].to_numpy(dtype=float)
    assert not np.allclose(medians, np.nanmedian(both, axis=0))
    assert not np.allclose(scaler.mean_, np.nanmean(both, axis=0))

    # transforming the shifted test set uses the TRAIN statistics (not re-fitted)
    Xt = pipe.named_steps["pre"].transform(X_te)
    first = (X_te[num].to_numpy(dtype=float)[:, 0] - scaler.mean_[0]) / scaler.scale_[0]
    finite = ~np.isnan(X_te[num[0]].to_numpy())
    np.testing.assert_allclose(Xt[finite, 0], first[finite], rtol=1e-10)


def test_missing_indicators_are_learned_on_train_only(env):
    cfg = env["cfg"]
    num, cat = _features(cfg, "A_keep_encode")
    parts = _parts(env)
    X_tr = parts["train"][num + cat].copy()
    X_tr["pain_value"] = X_tr["pain_value"].fillna(5.0)  # no missing pain in train
    X_te = parts["test"][num + cat].copy()
    X_te["pain_value"] = np.nan                            # all missing in test
    pipe = build_pipeline("dtree", {}, "none", cfg, cfg["variants"]["A_keep_encode"], seed=0, threads=1)
    pipe.fit(X_tr, parts["train"]["acuity"].to_numpy() - 1)
    names = list(pipe.named_steps["pre"].get_feature_names_out())
    assert "missingindicator_pain_value" not in names
    assert pipe.named_steps["pre"].transform(X_te).shape[1] == len(names)


def test_final_protocol_model_imputer_matches_train_partition(env, tmp_path):
    """The model persisted by run_task (logreg) carries medians of ITS train partition."""
    cfg = env["cfg"]
    ctx = make_ctx(cfg, env["prepared"], tmp_path)
    task = Task("A_keep_encode", 2, "logreg", "none")
    run_task(task, ctx)
    import joblib

    pipe = joblib.load(tmp_path / "tasks" / task.id / "private" / "model.joblib")
    num, _ = _features(cfg, "A_keep_encode")
    parts = load_task_data(ctx, "A_keep_encode", 2)
    medians = pipe.named_steps["pre"].named_transformers_["num"].named_steps["impute"].statistics_
    np.testing.assert_allclose(medians, np.nanmedian(parts["train"][num].to_numpy(dtype=float), axis=0))
    all_rows = pd.concat([parts[p] for p in PARTITIONS])[num].to_numpy(dtype=float)
    scaler = pipe.named_steps["pre"].named_transformers_["num"].named_steps["scale"]
    assert not np.allclose(scaler.mean_, np.nanmean(all_rows, axis=0), rtol=0, atol=1e-9)


# --------------------------------------------------------------------------- 3. resampling only in fit

class SpyClassifier(ClassifierMixin, BaseEstimator):
    """Records how many rows reach fit/predict; predicts the majority class."""

    def __init__(self, log=None):
        self.log = log

    def fit(self, X, y, sample_weight=None):
        self.classes_ = np.unique(y)
        vals, counts = np.unique(y, return_counts=True)
        self.majority_ = vals[np.argmax(counts)]
        self.fit_counts_ = dict(zip(vals.tolist(), counts.tolist(), strict=True))
        if self.log is not None:
            self.log.append(("fit", len(y), self.fit_counts_))
        return self

    def predict(self, X):
        if self.log is not None:
            self.log.append(("predict", X.shape[0], None))
        return np.full(X.shape[0], self.majority_)

    def predict_proba(self, X):
        p = np.zeros((X.shape[0], len(self.classes_)))
        p[:, np.searchsorted(self.classes_, self.majority_)] = 1.0
        return p


def test_oversample_only_in_fit(env):
    cfg = env["cfg"]
    parts = _parts(env)
    num, cat = _features(cfg, "A_keep_encode")
    y_tr = parts["train"]["acuity"].to_numpy() - 1
    log: list = []
    pipe = build_pipeline("dtree", {}, "oversample", cfg, cfg["variants"]["A_keep_encode"], seed=0, threads=1)
    pipe.set_params(model=SpyClassifier(log))
    pipe.fit(parts["train"][num + cat], y_tr)
    _, n_fit, counts = log[0]
    max_count = np.bincount(y_tr).max()
    assert n_fit == 5 * max_count > len(y_tr)
    assert set(counts.values()) == {max_count}          # every class balanced to the majority
    for part in ("val", "test"):
        pred = pipe.predict(parts[part][num + cat])
        assert len(pred) == len(parts[part])
        assert log[-1] == ("predict", len(parts[part]), None)


@pytest.mark.parametrize("strategy", ["none", "oversample"])
def test_subsample_cap_acts_on_fit_but_not_on_predict(env, strategy):
    cfg = env["cfg"]
    parts = _parts(env)
    num, cat = _features(cfg, "A_keep_encode")
    y_tr = parts["train"]["acuity"].to_numpy() - 1
    log: list = []
    cap = 150
    pipe = build_pipeline("svm_rbf", {}, strategy, cfg, cfg["variants"]["A_keep_encode"], seed=0, threads=1, cap=cap)
    assert "subsample" in pipe.named_steps
    pipe.set_params(model=SpyClassifier(log))
    pipe.fit(parts["train"][num + cat], y_tr)
    _, n_fit, counts = log[0]
    assert n_fit <= cap + 5 and n_fit < len(y_tr)
    assert set(counts) == {0, 1, 2, 3, 4}               # every class survives the cap
    pred = pipe.predict(parts["val"][num + cat])
    assert len(parts["val"]) > cap
    assert len(pred) == len(parts["val"])
    assert log[-1] == ("predict", len(parts["val"]), None)


def test_stratified_subsample_properties():
    rng = np.random.default_rng(0)
    y = rng.choice(5, size=5000, p=[0.06, 0.33, 0.53, 0.07, 0.01])
    X = np.arange(5000)[:, None].astype(float)
    Xs, ys = stratified_subsample(X, y, 500, seed=3)
    assert abs(len(ys) - 500) <= 5
    assert set(ys) == set(y)
    np.testing.assert_array_equal(y[Xs[:, 0].astype(int)], ys)       # rows stay aligned with labels
    assert len(np.unique(Xs[:, 0])) == len(Xs)                       # without replacement
    p_full = np.bincount(y, minlength=5) / len(y)
    p_sub = np.bincount(ys, minlength=5) / len(ys)
    np.testing.assert_allclose(p_sub, p_full, atol=0.01)
    Xs2, ys2 = stratified_subsample(X, y, 500, seed=3)
    np.testing.assert_array_equal(Xs, Xs2)
    # below the cap: identity
    Xi, yi = stratified_subsample(X[:100], y[:100], 500, seed=3)
    assert len(yi) == 100
    np.testing.assert_array_equal(Xi, X[:100])


def test_stratified_subsample_keeps_a_singleton_class():
    y = np.array([0] * 999 + [1])
    X = np.arange(1000)[:, None]
    _, ys = stratified_subsample(X, y, 50, seed=0)
    assert 1 in set(ys)


def test_protocol_oversample_predicts_every_val_and_test_row(env, tmp_path, monkeypatch):
    """End to end through run_task: the spy sees oversampled fits and full-size predictions."""
    log: list = []
    monkeypatch.setattr(imbalance, "make_estimator", lambda *a, **k: SpyClassifier(log))
    ctx = make_ctx(env["cfg"], env["prepared"], tmp_path)
    task = Task("A_keep_encode", 1, "dtree", "oversample")
    result = run_task(task, ctx)
    n = result["data"]
    fits = [e for e in log if e[0] == "fit"]
    preds = [e[1] for e in log if e[0] == "predict"]
    assert fits and all(nf > n["n_train"] for _, nf, _ in fits)
    assert set(preds) <= {n["n_val"], n["n_test"]}
    out = pd.read_parquet(tmp_path / "tasks" / task.id / "private" / "predictions.parquet")
    assert (out["partition"] == "val").sum() == n["n_val"]
    assert (out["partition"] == "test").sum() == n["n_test"]
    assert out["stay_id"].is_unique


# --------------------------------------------------------------------------- 4. no target / IDs as features

@pytest.mark.parametrize("column", FORBIDDEN_FEATURES)
@pytest.mark.parametrize("variant", ["A_keep_encode", "B_pain_numeric_only", "C_values_only"])
@pytest.mark.parametrize("kind", ["numeric_features", "categorical_features"])
def test_config_rejects_forbidden_feature(column, variant, kind):
    base = load_config(REPO / "configs" / "main.yaml")["variants"][variant][kind]
    value = "[" + ", ".join([*base, column]) + "]"
    with pytest.raises(ConfigError, match="forbidden"):
        load_config(REPO / "configs" / "main.yaml", overrides=[f"variants.{variant}.{kind}={value}"])


def test_renamed_target_is_also_forbidden():
    with pytest.raises(ConfigError, match="forbidden"):
        load_config(REPO / "configs" / "main.yaml",
                    overrides=["features.target=sbp"])  # sbp is a feature of every variant


@pytest.mark.parametrize("variant", ["A_keep_encode", "B_pain_numeric_only", "C_values_only"])
def test_columns_reaching_the_preprocessor_exclude_target_and_ids(env, tmp_path, monkeypatch, variant):
    seen: list[list[str]] = []
    original = protocol._fit_predict

    def spy(model, params, strategy, ctx, vcfg, seed, X_tr, y_tr_enc, X_eval_list, cap):
        seen.append(list(X_tr.columns))
        seen.extend(list(X.columns) for X in X_eval_list)
        return original(model, params, strategy, ctx, vcfg, seed, X_tr, y_tr_enc, X_eval_list, cap)

    monkeypatch.setattr(protocol, "_fit_predict", spy)
    task = Task(variant, 1, "dtree", "none")
    run_task(task, make_ctx(env["cfg"], env["prepared"], tmp_path))
    assert seen
    for cols in seen:
        assert not set(cols) & set(FORBIDDEN_FEATURES)
        assert not {"pain_raw", "pain_kind", "partition"} & set(cols)
    import joblib

    pipe = joblib.load(tmp_path / "tasks" / task.id / "private" / "model.joblib")
    names_in = set(pipe.named_steps["pre"].feature_names_in_)
    names_out = set(pipe.named_steps["pre"].get_feature_names_out())
    assert not names_in & set(FORBIDDEN_FEATURES)
    assert not any(f in name for name in names_out for f in FORBIDDEN_FEATURES)
    if variant == "C_values_only":
        assert not any(n.startswith("missingindicator") for n in names_out)
        assert "pain_status" not in names_in
