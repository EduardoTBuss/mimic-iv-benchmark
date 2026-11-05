"""Automatic campaign report: ``reports/campaigns/<id>/summary.md`` (+ figures, stats.json).

Results tables and automatic flags only; no scientific prose. Aggregates only, small cells masked.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from triagebench.reporting import figures
from triagebench.reporting.disclosure import mask_count
from triagebench.reporting.tables import md_table
from triagebench.utils.config import all_models, primary_variant
from triagebench.utils.io import atomic_write_json, atomic_write_text, read_json, utc_now

MAIN_METRICS = ["macro_f1", "balanced_accuracy", "qwk", "mae_ordinal", "recall_1", "recall_5",
                "under_triage_rate", "severe_under_triage_rate", "accuracy"]


def _ms(values: pd.Series) -> str:
    v = values.dropna()
    if v.empty:
        return "—"
    return f"{v.mean():.4f} ± {v.std(ddof=1):.4f}" if len(v) > 1 else f"{v.mean():.4f}"


def _main_table(metrics: pd.DataFrame, timings: pd.DataFrame, variant: str, order: list[str], strategies: list[str]) -> str:
    d = metrics[(metrics.variant == variant) & (metrics.split == "test")]
    rows = []
    for s in strategies:
        for m in order:
            sub = d[(d.model == m) & (d.strategy == s)]
            if sub.empty:
                continue
            t = timings[(timings.variant == variant) & (timings.model == m) & (timings.strategy == s)]
            rows.append([m, s, sub.seed.nunique()] + [_ms(sub[sub.metric == k].value) for k in MAIN_METRICS]
                        + [f"{t.final_fit_seconds.median():.1f}" if not t.empty else "—",
                           f"{1000 * (t.predict_test_seconds / t.n_test).median():.3f}" if not t.empty else "—"])
    return md_table(["modelo", "estratégia", "seeds"] + MAIN_METRICS + ["fit final (s, mediana)", "inferência (ms/1000 estadias)"], rows)


def _per_class_table(per_class: pd.DataFrame, variant: str, order: list[str]) -> str:
    d = per_class[(per_class.variant == variant) & (per_class.split == "test") & (per_class.strategy == "none")]
    rows = []
    for m in order:
        sub = d[d.model == m]
        if sub.empty:
            continue
        rows.append([m] + [f"{sub[sub.label == lab].recall.mean():.3f}" for lab in range(1, 6)]
                    + [f"{sub[sub.label == lab].precision.mean():.3f}" for lab in range(1, 6)])
    return md_table(["modelo"] + [f"recall {k}" for k in range(1, 6)] + [f"precision {k}" for k in range(1, 6)], rows)


def _error_distance_table(abs_error: pd.DataFrame, variant: str, order: list[str], k: int) -> str:
    d = abs_error[(abs_error.variant == variant) & (abs_error.split == "test") & (abs_error.strategy == "none")]
    rows = []
    for m in order:
        sub = d[d.model == m]
        if sub.empty:
            continue
        total = sub["count"].sum()
        cells = []
        for dist in range(5):
            c = int(sub[sub.distance == dist]["count"].sum())
            cells.append("<11" if 0 < c < k else f"{100 * c / total:.2f}%")
        rows.append([m, mask_count(total, k)] + cells)
    return md_table(["modelo", "estadias de teste (todas as seeds)"] + [f"|erro| = {i}" for i in range(5)], rows)


def _hpo_table(trials: pd.DataFrame, order: list[str]) -> str:
    if trials.empty:
        return "_sem trials_"
    rows = []
    for m in order:
        sub = trials[trials.model == m]
        if sub.empty:
            continue
        ok = sub[sub.status == "ok"]
        rows.append([m, len(sub), len(ok), int((sub.status == "error").sum()),
                     f"{100 * (ok.n_warnings.fillna(0) > 0).mean():.1f}%" if not ok.empty else "—",
                     f"{(ok.fit_seconds + ok.predict_val_seconds).median():.1f}" if not ok.empty else "—"])
    return md_table(["modelo", "trials", "ok", "erro", "% ok com warning", "s por trial (mediana)"], rows)


def _cost_table(cdir: Path) -> str:
    path = cdir / "tables" / "cost_benchmark.parquet"
    if not path.exists():
        return "_benchmark de custo sequencial não executado; ver tempos da campanha (com concorrência) na tabela principal._"
    cb = pd.read_parquet(path)
    if cb.empty:
        return "_vazio_"
    g = cb.groupby(["model", "strategy"]).agg(fit_s=("fit_seconds", "median"), fit_sd=("fit_seconds", "std"),
                                              pred_ms=("predict_ms_per_1000", "median"), reps=("repeat", "count")).reset_index()
    rows = [[r.model, r.strategy, int(r.reps), f"{r.fit_s:.2f}", "—" if np.isnan(r.fit_sd) else f"{r.fit_sd:.2f}", f"{r.pred_ms:.3f}"]
            for r in g.sort_values("fit_s", ascending=False).itertuples()]
    host = cb.host.iloc[0] if "host" in cb else "?"
    return (f"Refit sequencial com 1 thread das configurações congeladas (seed/variante do config), host `{host}`.\n\n"
            + md_table(["modelo", "estratégia", "repetições", "treino (s, mediana)", "DP", "inferência (ms/1000)"], rows))


def _strata_section(cfg: dict, cdir: Path, prepared_dir: Path | None, order: list[str], k: int) -> str:
    if not prepared_dir:
        return "_dados preparados indisponíveis nesta máquina_"
    from triagebench.analysis.strata import strata_markdown, stratified_test_metrics
    from triagebench.utils.io import atomic_write_parquet

    variants = [v for v, vc in cfg["variants"].items() if not vc.get("exclude_non_numeric_pain")]
    df = stratified_test_metrics(cdir, Path(prepared_dir), variants)
    if not df.empty:
        atomic_write_parquet(df, cdir / "tables" / "strata.parquet")
    return ("Completos = os 6 sinais vitais presentes e dor numérica. Ausência é um forte marcador de acuity 1 "
            "(padrão de documentação); compare o desempenho nos dois estratos.\n\n" + strata_markdown(df, order, k))


def _sensitivity_tables(cfg: dict, metrics: pd.DataFrame, timings: pd.DataFrame, order: list[str]) -> str:
    if metrics.empty:
        return "_—_"
    out = []
    primary = primary_variant(cfg)
    for name, vc in cfg["variants"].items():
        if name == primary or metrics[metrics.variant == name].empty:
            continue
        strategies = vc.get("strategies") or list(cfg["imbalance"]["strategies"])
        out += [f"### `{name}`", "", " ".join(str(vc.get("description", "")).split()), "",
                _main_table(metrics, timings, name, order, strategies), ""]
    return "\n".join(out) if out else "_sem resultados de sensibilidade_"


def _importance_section(cdir: Path) -> str:
    path = cdir / "tables" / "importance.parquet"
    if not path.exists():
        return "_não executada nesta campanha (`triagebench importance`)_"
    from triagebench.analysis.importance import importance_markdown

    return importance_markdown(pd.read_parquet(path))


def _h1_secondary_section(cfg: dict, metrics: pd.DataFrame, variant: str) -> str:
    if metrics.empty:
        return "_—_"
    from triagebench.analysis.secondary import h1_secondary_markdown, h1_validation_selected_strategy

    return h1_secondary_markdown(h1_validation_selected_strategy(metrics, cfg, variant))


def _decodings_section(cdir: Path, variant: str, order: list[str]) -> str:
    from triagebench.analysis.secondary import decodings, decodings_markdown
    from triagebench.utils.io import atomic_write_parquet

    df = decodings(cdir, variant)
    if not df.empty:
        atomic_write_parquet(df, cdir / "tables" / "decodings.parquet")
    return decodings_markdown(df, order)


def _anomalies_md(tables: dict, stats: dict | None, variant: str) -> str:
    items = []
    f = tables["failures"]
    if not f.empty:
        items.append(f"- **{len(f)} tarefa(s) com falha** (detalhes em `tables/failures.parquet` e `tasks/*/error.json`).")
    t = tables["timings"]
    if not t.empty and (t.n_warnings_final > 0).any():
        items.append(f"- {int((t.n_warnings_final > 0).sum())} ajuste(s) final(is) emitiram warnings (ex.: convergência).")
    if not t.empty and (t.hpo_n_error > 0).any():
        items.append(f"- {int((t.hpo_n_error > 0).sum())} tarefa(s) com configurações de HPO que falharam (o restante seguiu).")
    items.append("- Ausência informativa (auditoria F1): sinais vitais ausentes em 28–37% das estadias de acuity 1 vs ~1% na "
                 "classe 3; os indicadores de ausência permitem ao modelo usar o padrão de documentação, não só fisiologia.")
    items.append("- `pain` = 'critical'/'crit' é julgamento de gravidade da enfermagem (proxy do rótulo); fica em `other`.")
    if stats:
        for a in stats.get("anomalies", [])[:40]:
            items.append(f"- {a.get('type', a.get('kind', 'anomalia'))}: {', '.join(f'{k}={v}' for k, v in a.items() if k not in ('type', 'kind'))}")
    return "\n".join(items)


def write_reports(cfg: dict, cdir: Path, tables: dict, stats: dict | None, prepared_dir: Path | None) -> Path:
    cdir = Path(cdir)
    meta = read_json(cdir / "campaign.json")
    manifest = read_json(cdir / "manifest.json")
    out = Path(cfg["paths"]["reports"]) / "campaigns" / meta["campaign_id"]
    figdir = out / "figures"
    k = int(cfg["evaluation"]["disclosure_min_cell"])
    variant = primary_variant(cfg)
    order = all_models(cfg)
    strategies = list(cfg["imbalance"]["strategies"])
    metrics = tables["metrics"]

    if prepared_dir and (Path(prepared_dir) / "data_preparation.md").exists():
        out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(prepared_dir) / "data_preparation.md", out / "data_preparation.md")
    if stats is not None:
        atomic_write_json(out / "stats.json", stats)

    figs = []
    if not metrics.empty:
        figs += [figures.fig_metric_box(metrics, variant, "macro_f1", order, figdir / "macro_f1_by_model.png"),
                 figures.fig_metric_box(metrics, variant, "qwk", order, figdir / "qwk_by_model.png"),
                 figures.fig_strategy_effect(metrics, variant, "recall_1", order, strategies, figdir / "recall1_by_strategy.png"),
                 figures.fig_error_distance(tables["abs_error"], variant, order, figdir / "error_distance.png", k)]
        val = metrics[(metrics.variant == variant) & (metrics.split == "val") & (metrics.strategy == "none")
                      & (metrics.metric == "macro_f1") & metrics.model.isin(cfg["models"]["primary"])]
        if not val.empty:
            best = val.groupby("model").value.mean().idxmax()
            conf = tables["confusion"]
            c = conf[(conf.variant == variant) & (conf.split == "test") & (conf.strategy == "none") & (conf.model == best)]
            cm = c.groupby(["true", "pred"])["count"].sum().unstack(fill_value=0).reindex(index=range(1, 6), columns=range(1, 6), fill_value=0)
            figs.append(figures.fig_confusion(cm.to_numpy(), f"{best} (best primary by mean VALIDATION macro-F1), test, all seeds",
                                              figdir / "confusion_best_primary.png", k))
    figs = [f for f in figs if f is not None]

    sessions = manifest.get("sessions", [])
    git = {s["environment"]["git"].get("short") for s in sessions if s.get("environment")}
    hosts = {s["environment"]["hardware"]["hostname"] for s in sessions if s.get("environment")}
    seeds_done = sorted(metrics.seed.unique().tolist()) if not metrics.empty else []
    lines = [
        f"# Resumo da campanha `{meta['campaign_id']}`",
        "",
        f"> Gerado automaticamente em {utc_now()} por `triagebench analyze`. Só agregados; contagens de 1 a {k - 1} "
        f"mascaradas. Sem texto de artigo: tabelas, testes pré-registrados (`docs/analysis_plan.md`) e alertas.",
        "",
        "## Execução",
        "",
        md_table(["item", "valor"], [
            ["dataset", f"{meta['dataset']['name']} v{meta['dataset']['version']} (zip SHA256 `{meta['dataset']['zip_sha256'][:16]}…`)"],
            ["dados preparados", f"`{meta['prepared_id']}` (ver `data_preparation.md`)"],
            ["commits", ", ".join(sorted(g for g in git if g)) or "?"], ["máquinas", ", ".join(sorted(hosts)) or "?"],
            ["sessões", len(sessions)], ["seeds com resultado", ", ".join(map(str, seeds_done)) or "—"],
            ["tarefas concluídas", len(tables["timings"])], ["tarefas com falha", len(tables["failures"])],
            ["combinações não aplicáveis", len(tables["not_applicable"])],
            ["horas de tarefa (soma)", f"{tables['timings'].task_seconds.sum() / 3600:.1f}" if not tables["timings"].empty else "0"],
        ]),
        "",
        f"## Desempenho no teste — variante principal `{variant}` (média ± DP entre seeds)",
        "",
        _main_table(metrics, tables["timings"], variant, order, strategies) if not metrics.empty else "_sem resultados_",
        "",
        "Tempos desta tabela foram medidos com tarefas concorrentes; para custo use a seção de custo.",
        "",
        "## Recall e precisão por classe (teste, estratégia none)",
        "",
        _per_class_table(tables["per_class"], variant, order) if not tables["per_class"].empty else "_—_",
        "",
        "## Estratos do teste: sinais completos × incompletos (pré-registrado em 05/11)",
        "",
        _strata_section(cfg, cdir, prepared_dir, order, k),
        "",
        "## Variantes de sensibilidade (cada uma no seu próprio teste; B não é comparável diretamente com A)",
        "",
        _sensitivity_tables(cfg, metrics, tables["timings"], order),
        "",
        "## Distância ordinal dos acertos/erros (teste, estratégia none, todas as seeds)",
        "",
        _error_distance_table(tables["abs_error"], variant, order, k) if not tables["abs_error"].empty else "_—_",
        "",
    ]
    if stats is not None:
        from triagebench.analysis.stats import render_stats_markdown

        lines += ["## Análise pré-registrada", "", render_stats_markdown(stats), ""]
    lines += ["## Importância das variáveis por permutação agrupada (F5, teste, modelos escolhidos na validação)", "",
              _importance_section(cdir), "",
              "## Análises secundárias pré-registradas em 05/11 (descritivas)", "",
              "### H1 com a estratégia escolhida na validação", "",
              _h1_secondary_section(cfg, metrics, variant), "",
              "### Decodificações alternativas a partir das probabilidades salvas (teste, média entre seeds)", "",
              _decodings_section(cdir, variant, order), "",
              "## Custo computacional", "", _cost_table(cdir), "",
              "## Busca de hiperparâmetros", "", _hpo_table(tables["hpo_trials"], order), "",
              "## Alertas e anomalias", "", _anomalies_md(tables, stats, variant), "",
              "## Figuras", ""] + [f"- `figures/{Path(f).name}`" for f in figs] + [""]
    path = atomic_write_text(out / "summary.md", "\n".join(lines))
    if cfg["campaign"]["tag"] == "main":
        atomic_write_text(Path(cfg["paths"]["reports"]) / "summary.md",
                          f"# Resumo mais recente\n\nCampanha principal: [`{meta['campaign_id']}`](campaigns/{meta['campaign_id']}/summary.md)\n")
    return path
