"""Dataset audit that emits AGGREGATES ONLY (counts, percentages, quantiles).

``build_audit`` returns raw aggregate numbers (stored under outputs/, never in git);
``render_audit_markdown`` produces ``reports/data_audit.md`` with small cells (1..10) masked.
No row, identifier or individual record is ever printed.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from triagebench.data.schema import ACUITY_LEVELS, VITALS
from triagebench.preprocessing.pain import KINDS, PainRules, classify_pain, normalize_pain_string, parse_pain
from triagebench.reporting.disclosure import mask_count, mask_pct
from triagebench.reporting.tables import md_table

LEVEL_KEYS = [str(a) for a in ACUITY_LEVELS] + ["missing"]


def _acuity_counts(acuity: pd.Series) -> dict[str, int]:
    counts = {str(a): int((acuity == a).sum()) for a in ACUITY_LEVELS}
    counts["missing"] = int(acuity.isna().sum())
    return counts


def cramers_v(table: np.ndarray) -> float:
    table = np.asarray(table, dtype=float)
    table = table[:, table.sum(axis=0) > 0]
    if table.shape[1] < 2 or table.sum() == 0:
        return float("nan")
    chi2 = chi2_contingency(table, correction=False)[0]
    return float(math.sqrt(chi2 / (table.sum() * (min(table.shape) - 1))))


def _bands(x: pd.Series, r: dict) -> dict[str, pd.Series]:
    return {
        "below_outlier_low (NaN)": x < r["outlier_low"],
        "clip_to_valid_low": (x >= r["outlier_low"]) & (x < r["valid_low"]),
        "valid": (x >= r["valid_low"]) & (x <= r["valid_high"]),
        "clip_to_valid_high": (x > r["valid_high"]) & (x <= r["outlier_high"]),
        "above_outlier_high (NaN)": x > r["outlier_high"],
    }


def build_audit(triage: pd.DataFrame, load_report: dict, consistency: dict, ingest: dict, cfg: dict) -> dict:
    ccfg = cfg["cleaning"]
    k = int(cfg["evaluation"]["disclosure_min_cell"])
    acuity = triage["acuity_raw"]
    n = int(len(triage))
    audit: dict = {"n_rows": n, "disclosure_min_cell": k}

    audit["provenance"] = {
        "dataset": cfg["dataset"]["name"], "version": cfg["dataset"]["version"], "doi": cfg["dataset"]["doi"],
        "url": cfg["dataset"]["url"], "zip_name": ingest["zip_name"], "zip_sha256": ingest["zip_sha256"],
        "files": {rel: rec["sha256"] for rel, rec in ingest["files"].items()},
        "verified_at": ingest["verified_at"],
    }
    audit["load"] = load_report
    audit["consistency"] = consistency

    per_subject = triage.groupby("subject_id").size()
    buckets = [(1, 1), (2, 2), (3, 5), (6, 10), (11, 20), (21, 10**9)]
    audit["cohort"] = {
        "n_stays": int(triage["stay_id"].nunique()),
        "n_subjects": int(per_subject.size),
        "stays_per_subject_quantiles": {str(q): float(per_subject.quantile(q)) for q in (0.5, 0.9, 0.99, 0.999)},
        "stays_per_subject_mean": float(per_subject.mean()),
        "buckets": [
            {"visits": f"{lo}" if lo == hi else (f"{lo}-{hi}" if hi < 10**9 else f">={lo}"),
             "n_subjects": int(((per_subject >= lo) & (per_subject <= hi)).sum()),
             "n_stays": int(per_subject[(per_subject >= lo) & (per_subject <= hi)].sum())}
            for lo, hi in buckets
        ],
    }

    acu = _acuity_counts(acuity)
    acu["invalid_non_1_5"] = int((acuity.notna() & ~acuity.isin(ACUITY_LEVELS)).sum())
    audit["acuity"] = acu

    miss: dict = {}
    for var in [*VITALS, "pain_raw"]:
        m = triage[var].isna()
        miss[var] = {"overall": int(m.sum()), "by_acuity": {lv: int((m & (acuity == int(lv))).sum()) for lv in LEVEL_KEYS[:-1]}}
    miss["all_vitals_and_pain_missing"] = int(triage[[*VITALS, "pain_raw"]].isna().all(axis=1).sum())
    audit["missingness"] = miss

    quantiles = ccfg["audit"]["quantiles"]
    vitals: dict = {}
    for var in VITALS:
        x = triage[var]
        nonmiss = x.dropna()
        entry: dict = {
            "n_nonmissing": int(nonmiss.size),
            "quantiles": {str(q): float(nonmiss.quantile(q)) for q in quantiles} if nonmiss.size else {},
            "mean": float(nonmiss.mean()) if nonmiss.size else None,
            "zero_count": int((x == 0).sum()),
            "zero_by_acuity": _acuity_counts(acuity[x == 0]),
        }
        r = ccfg["ranges"][var]
        entry["xie_bands"] = {}
        for band, mask in _bands(x, r).items():
            entry["xie_bands"][band] = {"n": int(mask.sum()), "by_acuity": _acuity_counts(acuity[mask])}
        lo, hi = ccfg["clinical_reference"][var]
        below, above = x < lo, x > hi
        entry["clinical_reference"] = {
            "range": [lo, hi],
            "below": {"n": int(below.sum()), "by_acuity": _acuity_counts(acuity[below])},
            "above": {"n": int(above.sum()), "by_acuity": _acuity_counts(acuity[above])},
        }
        if var == "temperature":
            clo, chi = ccfg["celsius_like_range"]
            cmask = x.between(clo, chi)
            entry["celsius_like"] = {"range": [clo, chi], "n": int(cmask.sum()), "by_acuity": _acuity_counts(acuity[cmask]),
                                     "quantiles": {str(q): float(x[cmask].quantile(q)) for q in (0.05, 0.5, 0.95)} if cmask.sum() >= k else {}}
            gap = (x > chi) & (x < r["outlier_low"])
            entry["between_celsius_like_and_outlier_low"] = int(gap.sum())
        vitals[var] = entry
    audit["vitals"] = vitals

    bp = triage["dbp"].notna() & triage["sbp"].notna()
    ge = bp & (triage["dbp"] >= triage["sbp"])
    audit["blood_pressure"] = {"n_both_present": int(bp.sum()), "dbp_ge_sbp": int(ge.sum()),
                               "dbp_ge_sbp_by_acuity": _acuity_counts(acuity[ge])}

    rules = PainRules.from_config(ccfg["pain"])
    parsed = parse_pain(triage["pain_raw"], rules)
    kinds = parsed["pain_kind"]
    pain: dict = {"kinds": {}, "status": {}}
    for kind in KINDS:
        m = kinds == kind
        pain["kinds"][kind] = {"n": int(m.sum()), "by_acuity": _acuity_counts(acuity[m])}
    for status in rules.status_categories:
        m = parsed["pain_status"] == status
        pain["status"][status] = {"n": int(m.sum()), "by_acuity": _acuity_counts(acuity[m])}
    numeric_vals = parsed.loc[kinds == "numeric", "pain_value"]
    pain["numeric_value_counts"] = {str(int(v)): int((numeric_vals == v).sum()) for v in range(0, 11)}
    pain["numeric_non_integer"] = int((numeric_vals % 1 != 0).sum())
    raw = triage["pain_raw"]
    non_numeric = raw[raw.notna() & (kinds != "numeric")].map(normalize_pain_string)
    vc = non_numeric.value_counts()
    top_n = int(ccfg["audit"]["top_pain_strings"])
    frequent = vc[vc >= k]
    pain["n_distinct_non_numeric_strings"] = int(vc.size)
    unable_re = rules.unable_regex()
    pain["frequent_non_numeric_strings"] = [
        {"string": s, "n": int(c), "kind": classify_pain(s, rules, unable_re)[1]}
        for s, c in frequent.head(top_n).items()
    ]
    pain["rare_strings_total"] = int(vc[vc < k].sum())
    pain["rare_strings_distinct"] = int((vc < k).sum())
    audit["pain"] = pain

    labelled = acuity.isin(ACUITY_LEVELS)
    removed = labelled & (kinds != "numeric")
    table = np.array([[int((removed & (acuity == a)).sum()) for a in ACUITY_LEVELS],
                      [int((labelled & ~removed & (acuity == a)).sum()) for a in ACUITY_LEVELS]])
    class_n = table.sum(axis=0)
    rates = {str(a): (float(table[0, i] / class_n[i]) if class_n[i] else None) for i, a in enumerate(ACUITY_LEVELS)}
    valid_rates = [v for v in rates.values() if v is not None]
    overall = float(table[0].sum() / class_n.sum()) if class_n.sum() else float("nan")
    ratio = (max(valid_rates) / min(valid_rates)) if valid_rates and min(valid_rates) > 0 else float("inf")
    v = cramers_v(table)
    audit["variant_b_bias_check"] = {
        "rule": "B can be the primary analysis only if overall removal <= 5%, max/min class removal ratio <= 1.5 and Cramer's V < 0.05",
        "n_labelled": int(class_n.sum()),
        "removed_by_acuity": {str(a): int(table[0, i]) for i, a in enumerate(ACUITY_LEVELS)},
        "class_sizes": {str(a): int(class_n[i]) for i, a in enumerate(ACUITY_LEVELS)},
        "removal_rate_by_acuity": rates,
        "overall_removal_rate": overall,
        "max_min_ratio": ratio,
        "cramers_v": v,
        "b_can_be_primary": bool(overall <= 0.05 and ratio <= 1.5 and v < 0.05),
    }
    return audit


def _acuity_row(label: str, counts: dict, k: int, total: int | None = None) -> list[str]:
    row = [label] + [mask_count(counts.get(lv, 0), k) for lv in LEVEL_KEYS]
    n = sum(counts.get(lv, 0) for lv in LEVEL_KEYS)
    row.append(mask_count(n, k))
    if total is not None:
        row.append(mask_pct(n, total, k))
    return row


def render_audit_markdown(a: dict) -> str:
    k = a["disclosure_min_cell"]
    n = a["n_rows"]
    lv_head = ["acuity " + lv for lv in LEVEL_KEYS[:-1]] + ["acuity ausente"]
    out: list[str] = []
    p = a["provenance"]
    out += [
        "# Auditoria do dataset (somente agregados)",
        "",
        f"> Gerado automaticamente por `triagebench audit`. Contagens de 1 a {k - 1} aparecem como `<{k}`;",
        "> percentuais derivados delas aparecem como `—`. Nenhuma linha, identificador ou registro individual.",
        "",
        "## 1. Proveniência",
        "",
        md_table(["item", "valor"], [
            ["dataset", f"{p['dataset']} v{p['version']}"], ["DOI", p["doi"]], ["URL", p["url"]],
            ["arquivo", p["zip_name"]], ["SHA256 do zip", f"`{p['zip_sha256']}`"],
            ["SHA256 triage.csv.gz", f"`{p['files'].get('ed/triage.csv.gz')}`"],
            ["SHA256 edstays.csv.gz", f"`{p['files'].get('ed/edstays.csv.gz')}`"],
            ["verificação SHA256SUMS.txt", f"todos os {len(p['files'])} arquivos OK ({p['verified_at']})"],
        ]),
        "",
        "## 2. Schema e consistência",
        "",
        "Colunas de `triage` e `edstays` idênticas à documentação da v2.2 (checagem automática). `chiefcomplaint` nunca é carregada.",
        "",
        md_table(["checagem", "contagem"], [[key, mask_count(val, k)] for key, val in a["consistency"].items()]
                 + [[f"valor não numérico convertido em NaN: {var}", mask_count(c, k)]
                    for var, c in a["load"]["non_numeric_coerced"].items()]
                 + [["acuity não numérica", mask_count(a["load"]["acuity_non_numeric"], k)]]),
        "",
        "## 3. Coorte",
        "",
    ]
    c = a["cohort"]
    out += [
        md_table(["item", "valor"], [
            ["linhas na triage", mask_count(n, k)], ["estadias distintas", mask_count(c["n_stays"], k)],
            ["pacientes distintos (subject_id)", mask_count(c["n_subjects"], k)],
            ["estadias por paciente (média)", f"{c['stays_per_subject_mean']:.2f}"],
            ["estadias por paciente (mediana / p90 / p99 / p99.9)",
             " / ".join(f"{c['stays_per_subject_quantiles'][q]:.0f}" for q in ("0.5", "0.9", "0.99", "0.999"))],
        ]),
        "",
        md_table(["visitas por paciente", "pacientes", "estadias", "% das estadias"],
                 [[b["visits"], mask_count(b["n_subjects"], k), mask_count(b["n_stays"], k), mask_pct(b["n_stays"], n, k)]
                  for b in c["buckets"]]),
        "",
        "## 4. Distribuição de `acuity` (alvo)",
        "",
    ]
    acu = a["acuity"]
    out += [
        md_table(["acuity", "estadias", "%"], [[lv if lv != "missing" else "ausente", mask_count(acu[lv], k), mask_pct(acu[lv], n, k)] for lv in LEVEL_KEYS]
                 + [["fora de 1..5", mask_count(acu["invalid_non_1_5"], k), mask_pct(acu["invalid_non_1_5"], n, k)]]),
        "",
        "## 5. Ausentes por variável",
        "",
    ]
    rows = []
    for var, m in a["missingness"].items():
        if var == "all_vitals_and_pain_missing":
            continue
        rows.append([var, mask_count(m["overall"], k), mask_pct(m["overall"], n, k)]
                    + [mask_pct(m["by_acuity"][lv], acu[lv], k) for lv in LEVEL_KEYS[:-1]])
    out += [md_table(["variável", "ausentes", "% geral"] + [f"% em acuity {lv}" for lv in LEVEL_KEYS[:-1]], rows), "",
            f"Estadias sem nenhum dos 6 sinais vitais nem dor: {mask_count(a['missingness']['all_vitals_and_pain_missing'], k)}.", "",
            "## 6. Sinais vitais: distribuição e faixas", "",
            "Faixas de Xie et al. (2022) (temperatura convertida para °F): abaixo/acima do limite de outlier → NaN; "
            "entre o limite de outlier e o limite válido → valor cortado no limite. A faixa clínica é só referência de auditoria.", ""]
    for var, e in a["vitals"].items():
        out += [f"### {var}", ""]
        qs = e["quantiles"]
        out += [md_table(["n não ausentes", "média"] + [f"q{q}" for q in qs],
                         [[mask_count(e["n_nonmissing"], k), f"{e['mean']:.2f}" if e["mean"] is not None else "—"]
                          + [f"{v:.1f}" for v in qs.values()]]), ""]
        rows = [_acuity_row(band, d["by_acuity"], k, e["n_nonmissing"]) for band, d in e["xie_bands"].items()]
        lo, hi = e["clinical_reference"]["range"]
        rows.append(_acuity_row(f"clínica: abaixo de {lo}", e["clinical_reference"]["below"]["by_acuity"], k, e["n_nonmissing"]))
        rows.append(_acuity_row(f"clínica: acima de {hi}", e["clinical_reference"]["above"]["by_acuity"], k, e["n_nonmissing"]))
        rows.append(_acuity_row("valor exatamente 0", e["zero_by_acuity"], k, e["n_nonmissing"]))
        if "celsius_like" in e:
            cl = e["celsius_like"]
            rows.append(_acuity_row(f"parece °C: {cl['range'][0]}–{cl['range'][1]}", cl["by_acuity"], k, e["n_nonmissing"]))
        out += [md_table(["faixa"] + lv_head + ["total", "% dos não ausentes"], rows), ""]
        if "celsius_like" in e and e["celsius_like"].get("quantiles"):
            qv = e["celsius_like"]["quantiles"]
            out += [f"Valores com cara de °C: q0.05 / mediana / q0.95 = {qv['0.05']:.1f} / {qv['0.5']:.1f} / {qv['0.95']:.1f}. "
                    f"Entre a faixa °C e o limite de outlier: {mask_count(e['between_celsius_like_and_outlier_low'], k)}.", ""]
    bp = a["blood_pressure"]
    out += ["### Pressão: diastólica ≥ sistólica", "",
            md_table(["caso"] + lv_head + ["total", "% com ambas presentes"],
                     [_acuity_row("dbp ≥ sbp", bp["dbp_ge_sbp_by_acuity"], k, bp["n_both_present"])]), ""]
    pa = a["pain"]
    out += ["## 7. `pain` (texto livre desde a v2.0)", "",
            "Classificação automática de cada valor bruto (os textos originais são preservados no dado privado).", "",
            md_table(["tipo (parser)"] + lv_head + ["total", "%"],
                     [_acuity_row(kind, d["by_acuity"], k, n) for kind, d in pa["kinds"].items()]), "",
            md_table(["status (feature do modelo)"] + lv_head + ["total", "%"],
                     [_acuity_row(s, d["by_acuity"], k, n) for s, d in pa["status"].items()]), "",
            "Valores numéricos inteiros 0–10:", "",
            md_table(["dor"] + list(pa["numeric_value_counts"]),
                     [["estadias"] + [mask_count(v, k) for v in pa["numeric_value_counts"].values()]]), "",
            f"Numéricos não inteiros (ex.: 7.5): {mask_count(pa['numeric_non_integer'], k)}.", "",
            f"Strings não numéricas distintas: {mask_count(pa['n_distinct_non_numeric_strings'], k)}. "
            f"Abaixo, só as que aparecem ≥ {k} vezes (normalizadas: minúsculas, espaços colapsados); "
            f"as raras somam {mask_count(pa['rare_strings_total'], k)} estadias em "
            f"{mask_count(pa['rare_strings_distinct'], k)} strings.", "",
            md_table(["string normalizada", "estadias", "tipo atribuído"],
                     [[f"`{d['string']}`", mask_count(d["n"], k), d["kind"]] for d in pa["frequent_non_numeric_strings"]]), ""]
    b = a["variant_b_bias_check"]
    out += ["## 8. Viés da variante B (remover `pain` não numérico)", "",
            f"Regra pré-registrada: {b['rule']}.", "",
            md_table(["acuity", "estadias", "removidas em B", "% removida"],
                     [[lv, mask_count(b["class_sizes"][lv], k), mask_count(b["removed_by_acuity"][lv], k),
                       mask_pct(b["removed_by_acuity"][lv], b["class_sizes"][lv], k)] for lv in LEVEL_KEYS[:-1]]), "",
            md_table(["indicador", "valor"], [
                ["remoção total", f"{100 * b['overall_removal_rate']:.2f}%"],
                ["razão máx/mín entre classes", f"{b['max_min_ratio']:.2f}"],
                ["V de Cramér (removida × acuity)", f"{b['cramers_v']:.4f}"],
                ["B pode ser a análise principal?", "sim" if b["b_can_be_primary"] else "**não** → A é a principal; B fica como sensibilidade"],
            ]), ""]
    return "\n".join(out) + "\n"
