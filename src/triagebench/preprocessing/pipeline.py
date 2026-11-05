"""Leak-free preprocessing: every statistic (median, mean, std) is learned inside ``fit`` on the
training partition only, through a scikit-learn ``ColumnTransformer``."""

from __future__ import annotations

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def build_preprocessor(numeric: list[str], categorical: list[str], categories: dict[str, list[str]],
                       scale: bool, missing_indicators: bool = True) -> ColumnTransformer:
    """Median imputation (+ standardisation) of numeric values, 0/1 missing indicators kept
    UNSCALED (scaled rare indicators would dominate distances in KNN/SVM), and a fixed-category
    one-hot encoding for categorical columns (unknown categories ignored)."""
    num_steps: list = [("impute", SimpleImputer(strategy="median"))]
    if scale:
        num_steps.append(("scale", StandardScaler()))
    transformers: list = [("num", Pipeline(num_steps), list(numeric))]
    if missing_indicators:
        transformers.append(("missing", MissingIndicator(features="missing-only", error_on_new=False), list(numeric)))
    if categorical:
        transformers.append((
            "cat",
            OneHotEncoder(categories=[list(categories[c]) for c in categorical], handle_unknown="ignore",
                          sparse_output=False, dtype=np.float64),
            list(categorical),
        ))
    return ColumnTransformer(transformers, remainder="drop", sparse_threshold=0.0, verbose_feature_names_out=False)
