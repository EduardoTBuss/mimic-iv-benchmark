"""Reporting units, using fabricated timings and metrics only."""

import pandas as pd

from triagebench.reporting.summary import _main_table


def test_inference_time_is_milliseconds_per_thousand_stays():
    # Two seconds for 1,000 stays means 2,000 ms/1,000 stays.
    metrics = pd.DataFrame([
        {"variant": "A", "split": "test", "model": "logreg", "strategy": "none",
         "seed": 1, "metric": "macro_f1", "value": 0.5},
    ])
    timings = pd.DataFrame([
        {"variant": "A", "model": "logreg", "strategy": "none",
         "final_fit_seconds": 1.0, "predict_test_seconds": 2.0, "n_test": 1000},
    ])

    table = _main_table(metrics, timings, "A", ["logreg"], ["none"])

    assert "inferência (ms/1000 estadias)" in table
    row = next(line for line in table.splitlines() if line.startswith("| logreg |"))
    assert row.split("|")[-2].strip() == "2000.000"
