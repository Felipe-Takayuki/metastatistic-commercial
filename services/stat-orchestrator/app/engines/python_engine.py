"""Engine B comercial: cálculos estatísticos em Pure Python e SciPy (100% não-AGPL).

Gera tabelas estruturadas de acordo com as normas da 7ª edição da APA
(American Psychological Association).
"""
import math
from pathlib import Path
from typing import Any

import numpy as np

try:
    import scipy.stats as stats
    SCIPY_AVAILABLE = True
except ImportError:
    stats = None  # type: ignore
    SCIPY_AVAILABLE = False

try:
    import pyarrow.parquet as pq
    PYARROW_AVAILABLE = True
except ImportError:
    pq = None  # type: ignore
    PYARROW_AVAILABLE = False

from app.config import settings
from app.engines.base import StatisticalEngine


def _t_pvalue(t_val: float, df: int) -> float:
    """Calcula p-valor bicaudal da distribuição t de Student."""
    if math.isnan(t_val) or df <= 0:
        return float("nan")
    if SCIPY_AVAILABLE:
        return float(stats.t.sf(abs(t_val), df) * 2)
    # Aproximação normal para graus de liberdade elevados como fallback
    z = abs(t_val)
    return float(2.0 * (1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))))


def _t_crit(level: float, df: int) -> float:
    """Calcula valor crítico t para o nível de confiança (ex.: 0.95 -> 0.975)."""
    alpha = (1.0 - level) / 2.0
    p = 1.0 - alpha
    if SCIPY_AVAILABLE and df > 0:
        return float(stats.t.ppf(p, df))
    return 1.95996


def _f_pvalue(f_val: float, df1: int, df2: int) -> float:
    """Calcula p-valor unicaudal da distribuição F de Snedecor."""
    if math.isnan(f_val) or df1 <= 0 or df2 <= 0 or f_val < 0:
        return float("nan")
    if SCIPY_AVAILABLE:
        return float(stats.f.sf(f_val, df1, df2))
    # Fallback aproximado
    return 0.05 if f_val > 1.0 else 0.50


def _build_field(name: str, title: str, ftype: str = "number", fmt: str | None = None) -> dict[str, Any]:
    f: dict[str, Any] = {"name": name, "title": title, "type": ftype}
    if fmt is not None:
        f["format"] = fmt
    return f


def _build_apa_table(
    title: str,
    fields: list[dict[str, Any]],
    data: list[dict[str, Any]],
    notes: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    footnotes = [
        {
            "symbol": "<em>Nota.</em>",
            "text": "Análise processada pelo Engine B comercial (Python/SciPy puro, 100% não-AGPL). Formatação APA 7th.",
        }
    ]
    if notes:
        footnotes.extend(notes)
    return {
        "title": title,
        "schema": {"fields": fields},
        "data": data,
        "footnotes": footnotes,
    }


class PythonStatisticalEngine(StatisticalEngine):
    """Motor estatístico comercial implementado em Python/SciPy puro."""

    SUPPORTED_ANALYSES = {
        "descriptives",
        "Descriptives",
        "ttest_independent",
        "TTestIndependentSamples",
        "ttest_onesample",
        "TTestOneSample",
        "anova",
        "Anova",
        "correlation",
        "Correlation",
    }

    @property
    def name(self) -> str:
        return "python"

    def supports(self, analysis: str) -> bool:
        return analysis in self.SUPPORTED_ANALYSES

    async def health(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "engine": "python_engine_b",
            "scipy_available": SCIPY_AVAILABLE,
            "pyarrow_available": PYARROW_AVAILABLE,
            "supported_analyses": sorted(list(self.SUPPORTED_ANALYSES)),
        }

    def _extract_dataset_columns(self, payload: dict[str, Any]) -> dict[str, list[Any]]:
        """Extrai dados de payload em memória ou lê do arquivo Parquet compartilhado."""
        # 1. Dados em memória fornecidos no payload
        if "data" in payload and isinstance(payload["data"], dict):
            return {str(k): list(v) for k, v in payload["data"].items()}
        if "dataset" in payload and isinstance(payload["dataset"], dict):
            return {str(k): list(v) for k, v in payload["dataset"].items()}
        if "data" in payload and isinstance(payload["data"], list):
            # Lista de dicionários por linha
            rows = payload["data"]
            cols: dict[str, list[Any]] = {}
            if rows:
                for k in rows[0].keys():
                    cols[k] = [r.get(k) for r in rows]
            return cols

        # 2. Leitura do Parquet pelo dataset_id
        dataset_id = payload.get("dataset_id")
        if not dataset_id:
            raise ValueError("Nenhum dado ou dataset_id foi fornecido para análise.")

        path = Path(settings.data_dir) / "datasets" / f"{dataset_id}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Arquivo do dataset não encontrado: {path}")

        req_cols = payload.get("columns")
        if PYARROW_AVAILABLE:
            tbl = pq.read_table(path, columns=req_cols if req_cols else None)
            return {name: tbl[name].to_pylist() for name in tbl.column_names}
        else:
            raise RuntimeError("Leitura de arquivos Parquet exige biblioteca pyarrow instalada.")

    async def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        analysis = payload.get("analysis", "")
        options = payload.get("options", {})
        data_cols = self._extract_dataset_columns(payload)

        norm_name = analysis.lower().replace("samples", "").replace(" ", "_")

        if norm_name in ("descriptives", "descriptive"):
            return self._run_descriptives(data_cols, options)
        elif "ttestindependent" in norm_name or norm_name in ("ttest_independent", "ttest_ind"):
            return self._run_ttest_independent(data_cols, options)
        elif "ttestonesample" in norm_name or norm_name in ("ttest_onesample", "ttest_one"):
            return self._run_ttest_onesample(data_cols, options)
        elif norm_name in ("anova", "anova_oneway"):
            return self._run_anova(data_cols, options)
        elif norm_name in ("correlation", "correlation_pearson"):
            return self._run_correlation(data_cols, options)
        else:
            raise ValueError(f"Análise '{analysis}' não é suportada pelo Engine B (Python).")

    # -------------------------------------------------------------------------
    # 1. Estatísticas Descritivas
    # -------------------------------------------------------------------------
    def _run_descriptives(self, data_cols: dict[str, list[Any]], options: dict[str, Any]) -> dict[str, Any]:
        vars_requested = options.get("variables")
        if not vars_requested:
            vars_requested = list(data_cols.keys())
        elif isinstance(vars_requested, str):
            vars_requested = [vars_requested]

        rows = []
        for var in vars_requested:
            if var not in data_cols:
                continue
            raw_vals = data_cols[var]
            clean = []
            for v in raw_vals:
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    try:
                        clean.append(float(v))
                    except (ValueError, TypeError):
                        pass

            n = len(clean)
            if n == 0:
                rows.append({
                    "variable": var,
                    "n": 0,
                    "mean": None,
                    "sd": None,
                    "median": None,
                    "variance": None,
                    "min": None,
                    "max": None,
                })
                continue

            arr = np.array(clean, dtype=float)
            mean_val = float(np.mean(arr))
            sd_val = float(np.std(arr, ddof=1)) if n > 1 else 0.0
            var_val = float(np.var(arr, ddof=1)) if n > 1 else 0.0
            median_val = float(np.median(arr))
            min_val = float(np.min(arr))
            max_val = float(np.max(arr))

            rows.append({
                "variable": var,
                "n": n,
                "mean": round(mean_val, 4),
                "sd": round(sd_val, 4),
                "median": round(median_val, 4),
                "variance": round(var_val, 4),
                "min": round(min_val, 4),
                "max": round(max_val, 4),
            })

        fields = [
            _build_field("variable", "Variável", "string"),
            _build_field("n", "N", "integer"),
            _build_field("mean", "Média", "number", "dp:3"),
            _build_field("sd", "Desvio Padrão", "number", "dp:3"),
            _build_field("median", "Mediana", "number", "dp:3"),
            _build_field("variance", "Variância", "number", "dp:3"),
            _build_field("min", "Mínimo", "number", "dp:3"),
            _build_field("max", "Máximo", "number", "dp:3"),
        ]

        table = _build_apa_table("Estatísticas Descritivas", fields, rows)
        return {
            "status": "complete",
            "results": {
                ".meta": [{"name": "descriptives", "type": "table", "title": "Estatísticas Descritivas"}],
                "descriptives": table,
            },
        }

    # -------------------------------------------------------------------------
    # 2. Teste t Independente
    # -------------------------------------------------------------------------
    def _run_ttest_independent(self, data_cols: dict[str, list[Any]], options: dict[str, Any]) -> dict[str, Any]:
        dep_var = options.get("dependent")
        if isinstance(dep_var, list) and dep_var:
            dep_var = dep_var[0]
        group_var = options.get("group") or options.get("grouping_variable")

        if not dep_var or not group_var:
            raise ValueError("As opções 'dependent' e 'group' são obrigatórias para o Teste t Independente.")

        if dep_var not in data_cols or group_var not in data_cols:
            raise ValueError(f"Colunas '{dep_var}' ou '{group_var}' não encontradas no dataset.")

        y_raw = data_cols[dep_var]
        g_raw = data_cols[group_var]

        # Separação por grupos válidos
        pairs: list[tuple[float, str]] = []
        for y, g in zip(y_raw, g_raw):
            if y is not None and g is not None:
                try:
                    yf = float(y)
                    if not math.isnan(yf):
                        pairs.append((yf, str(g)))
                except (ValueError, TypeError):
                    continue

        groups = sorted(list({p[1] for p in pairs}))
        if len(groups) != 2:
            raise ValueError(f"A variável de agrupamento '{group_var}' deve conter exatamente 2 níveis (encontrados: {len(groups)}).")

        g1_name, g2_name = groups[0], groups[1]
        y1 = np.array([p[0] for p in pairs if p[1] == g1_name], dtype=float)
        y2 = np.array([p[0] for p in pairs if p[1] == g2_name], dtype=float)

        n1, n2 = len(y1), len(y2)
        if n1 < 1 or n2 < 1:
            raise ValueError("Cada grupo precisa de pelo menos 1 observação.")

        m1, m2 = float(np.mean(y1)), float(np.mean(y2))
        s1 = float(np.std(y1, ddof=1)) if n1 > 1 else 0.0
        s2 = float(np.std(y2, ddof=1)) if n2 > 1 else 0.0

        df = n1 + n2 - 2
        diff = m1 - m2

        if df > 0:
            pooled_var = ((n1 - 1) * (s1 ** 2) + (n2 - 1) * (s2 ** 2)) / df
            se_diff = math.sqrt(pooled_var * (1.0 / n1 + 1.0 / n2))
            pooled_sd = math.sqrt(pooled_var)
            cohen_d = diff / pooled_sd if pooled_sd > 0 else 0.0
            t_val = diff / se_diff if se_diff > 0 else 0.0
            p_val = _t_pvalue(t_val, df)
            t_critical = _t_crit(0.95, df)
            ci_lower = diff - t_critical * se_diff
            ci_upper = diff + t_critical * se_diff
        else:
            se_diff = 0.0
            cohen_d = 0.0
            t_val = 0.0
            p_val = 1.0
            ci_lower = diff
            ci_upper = diff

        row = {
            "variable": dep_var,
            "comparison": f"{g1_name} − {g2_name}",
            "t": round(t_val, 4),
            "df": df,
            "p": round(p_val, 6),
            "mean_diff": round(diff, 4),
            "se_diff": round(se_diff, 4),
            "cohen_d": round(cohen_d, 4),
            "ci_lower": round(ci_lower, 4),
            "ci_upper": round(ci_upper, 4),
        }

        fields = [
            _build_field("variable", "Variável", "string"),
            _build_field("comparison", "Comparação", "string"),
            _build_field("t", "t", "number", "dp:3"),
            _build_field("df", "gl", "integer"),
            _build_field("p", "p", "pvalue", "dp:3;p:.001"),
            _build_field("mean_diff", "Diferença média", "number", "dp:3"),
            _build_field("se_diff", "EP da diferença", "number", "dp:3"),
            _build_field("cohen_d", "d de Cohen", "number", "dp:3"),
            _build_field("ci_lower", "IC 95%: inferior", "number", "dp:3"),
            _build_field("ci_upper", "IC 95%: superior", "number", "dp:3"),
        ]

        notes = [
            {
                "symbol": "<em>Nota.</em>",
                "text": f"Hipótese alternativa bicaudal (diferença entre {g1_name} e {g2_name}). Variâncias combinadas.",
            }
        ]

        table = _build_apa_table("Teste t para Amostras Independentes", fields, [row], notes)
        return {
            "status": "complete",
            "results": {
                ".meta": [{"name": "ttest_independent", "type": "table", "title": "Teste t para Amostras Independentes"}],
                "ttest_independent": table,
            },
        }

    # -------------------------------------------------------------------------
    # 3. Teste t de Uma Amostra
    # -------------------------------------------------------------------------
    def _run_ttest_onesample(self, data_cols: dict[str, list[Any]], options: dict[str, Any]) -> dict[str, Any]:
        vars_requested = options.get("variables") or options.get("dependent")
        test_val = float(options.get("test_value", 0.0))

        if not vars_requested:
            raise ValueError("A opção 'variables' ou 'dependent' é obrigatória para o Teste t de Uma Amostra.")
        if isinstance(vars_requested, str):
            vars_requested = [vars_requested]

        rows = []
        for var in vars_requested:
            if var not in data_cols:
                continue
            clean = []
            for v in data_cols[var]:
                if v is not None:
                    try:
                        vf = float(v)
                        if not math.isnan(vf):
                            clean.append(vf)
                    except (ValueError, TypeError):
                        pass

            n = len(clean)
            if n < 2:
                rows.append({
                    "variable": var,
                    "test_value": test_val,
                    "t": None,
                    "df": max(0, n - 1),
                    "p": None,
                    "mean_diff": None,
                    "se_diff": None,
                    "cohen_d": None,
                    "ci_lower": None,
                    "ci_upper": None,
                })
                continue

            arr = np.array(clean, dtype=float)
            m = float(np.mean(arr))
            s = float(np.std(arr, ddof=1))
            df = n - 1
            se = s / math.sqrt(n) if n > 0 else 0.0
            diff = m - test_val
            t_val = diff / se if se > 0 else 0.0
            p_val = _t_pvalue(t_val, df)
            cohen_d = diff / s if s > 0 else 0.0
            t_critical = _t_crit(0.95, df)
            ci_lower = diff - t_critical * se
            ci_upper = diff + t_critical * se

            rows.append({
                "variable": var,
                "test_value": round(test_val, 4),
                "t": round(t_val, 4),
                "df": df,
                "p": round(p_val, 6),
                "mean_diff": round(diff, 4),
                "se_diff": round(se, 4),
                "cohen_d": round(cohen_d, 4),
                "ci_lower": round(ci_lower, 4),
                "ci_upper": round(ci_upper, 4),
            })

        fields = [
            _build_field("variable", "Variável", "string"),
            _build_field("test_value", "Valor de Teste", "number", "dp:3"),
            _build_field("t", "t", "number", "dp:3"),
            _build_field("df", "gl", "integer"),
            _build_field("p", "p", "pvalue", "dp:3;p:.001"),
            _build_field("mean_diff", "Diferença média", "number", "dp:3"),
            _build_field("se_diff", "EP da diferença", "number", "dp:3"),
            _build_field("cohen_d", "d de Cohen", "number", "dp:3"),
            _build_field("ci_lower", "IC 95%: inferior", "number", "dp:3"),
            _build_field("ci_upper", "IC 95%: superior", "number", "dp:3"),
        ]

        notes = [
            {
                "symbol": "<em>Nota.</em>",
                "text": f"Teste t de Student para uma amostra contra valor de referência μ₀ = {test_val}.",
            }
        ]

        table = _build_apa_table("Teste t para Uma Amostra", fields, rows, notes)
        return {
            "status": "complete",
            "results": {
                ".meta": [{"name": "ttest_onesample", "type": "table", "title": "Teste t para Uma Amostra"}],
                "ttest_onesample": table,
            },
        }

    # -------------------------------------------------------------------------
    # 4. ANOVA One-Way
    # -------------------------------------------------------------------------
    def _run_anova(self, data_cols: dict[str, list[Any]], options: dict[str, Any]) -> dict[str, Any]:
        dep_var = options.get("dependent")
        if isinstance(dep_var, list) and dep_var:
            dep_var = dep_var[0]
        factor_var = options.get("fixed_factors") or options.get("group") or options.get("factor")
        if isinstance(factor_var, list) and factor_var:
            factor_var = factor_var[0]

        if not dep_var or not factor_var:
            raise ValueError("As opções 'dependent' e 'fixed_factors' (ou 'group') são obrigatórias para ANOVA One-Way.")

        if dep_var not in data_cols or factor_var not in data_cols:
            raise ValueError(f"Colunas '{dep_var}' ou '{factor_var}' não encontradas no dataset.")

        y_raw = data_cols[dep_var]
        f_raw = data_cols[factor_var]

        # Agrupamento
        group_data: dict[str, list[float]] = {}
        for y, f in zip(y_raw, f_raw):
            if y is not None and f is not None:
                try:
                    yf = float(y)
                    if not math.isnan(yf):
                        group_data.setdefault(str(f), []).append(yf)
                except (ValueError, TypeError):
                    continue

        k = len(group_data)
        if k < 2:
            raise ValueError(f"A ANOVA One-Way requer pelo menos 2 grupos (encontrados: {k}).")

        all_y = []
        for g_vals in group_data.values():
            all_y.extend(g_vals)

        n_total = len(all_y)
        if n_total <= k:
            raise ValueError("Número insuficiente de observações em relação ao número de grupos.")

        grand_mean = float(np.mean(all_y))

        # Soma dos quadrados entre grupos (SS_between)
        ss_between = 0.0
        for g_vals in group_data.values():
            n_j = len(g_vals)
            if n_j > 0:
                mean_j = float(np.mean(g_vals))
                ss_between += n_j * ((mean_j - grand_mean) ** 2)

        # Soma dos quadrados dentro dos grupos (SS_within / residual)
        ss_within = 0.0
        for g_vals in group_data.values():
            if len(g_vals) > 0:
                mean_j = float(np.mean(g_vals))
                for y in g_vals:
                    ss_within += (y - mean_j) ** 2

        ss_total = ss_between + ss_within
        df1 = k - 1
        df2 = n_total - k

        ms_between = ss_between / df1 if df1 > 0 else 0.0
        ms_within = ss_within / df2 if df2 > 0 else 0.0

        f_val = ms_between / ms_within if ms_within > 0 else float("nan")
        p_val = _f_pvalue(f_val, df1, df2)
        eta_sq = ss_between / ss_total if ss_total > 0 else 0.0

        rows = [
            {
                "cases": factor_var,
                "ss": round(ss_between, 4),
                "df": df1,
                "ms": round(ms_between, 4),
                "f": round(f_val, 4) if not math.isnan(f_val) else None,
                "p": round(p_val, 6) if not math.isnan(p_val) else None,
                "eta_sq": round(eta_sq, 4),
            },
            {
                "cases": "Resíduos",
                "ss": round(ss_within, 4),
                "df": df2,
                "ms": round(ms_within, 4),
                "f": None,
                "p": None,
                "eta_sq": None,
            },
        ]

        fields = [
            _build_field("cases", "Casos", "string"),
            _build_field("ss", "Soma dos Quadrados", "number", "dp:3"),
            _build_field("df", "gl", "integer"),
            _build_field("ms", "Quadrado Médio", "number", "dp:3"),
            _build_field("f", "F", "number", "dp:3"),
            _build_field("p", "p", "pvalue", "dp:3;p:.001"),
            _build_field("eta_sq", "η² (Eta-quadrado)", "number", "dp:3"),
        ]

        table = _build_apa_table("ANOVA One-Way (Entre Grupos)", fields, rows)
        return {
            "status": "complete",
            "results": {
                ".meta": [{"name": "anova", "type": "table", "title": "ANOVA One-Way"}],
                "anova": table,
            },
        }

    # -------------------------------------------------------------------------
    # 5. Correlação de Pearson
    # -------------------------------------------------------------------------
    def _run_correlation(self, data_cols: dict[str, list[Any]], options: dict[str, Any]) -> dict[str, Any]:
        vars_requested = options.get("variables")
        if not vars_requested or len(vars_requested) < 2:
            num_cols = [k for k in data_cols.keys() if len(data_cols[k]) > 0]
            if len(num_cols) >= 2:
                vars_requested = num_cols[:2]
            else:
                raise ValueError("A Correlação de Pearson requer pelo menos duas variáveis em 'variables'.")

        rows = []
        for i in range(len(vars_requested)):
            for j in range(i + 1, len(vars_requested)):
                v1, v2 = vars_requested[i], vars_requested[j]
                if v1 not in data_cols or v2 not in data_cols:
                    continue

                pairs: list[tuple[float, float]] = []
                for x, y in zip(data_cols[v1], data_cols[v2]):
                    if x is not None and y is not None:
                        try:
                            xf, yf = float(x), float(y)
                            if not math.isnan(xf) and not math.isnan(yf):
                                pairs.append((xf, yf))
                        except (ValueError, TypeError):
                            continue

                n = len(pairs)
                if n < 3:
                    rows.append({
                        "var1": v1,
                        "var2": v2,
                        "r": None,
                        "t": None,
                        "df": max(0, n - 2),
                        "p": None,
                        "n": n,
                        "ci_lower": None,
                        "ci_upper": None,
                    })
                    continue

                arr_x = np.array([p[0] for p in pairs], dtype=float)
                arr_y = np.array([p[1] for p in pairs], dtype=float)

                if SCIPY_AVAILABLE:
                    res = stats.pearsonr(arr_x, arr_y)
                    r_val = float(res.statistic)
                    p_val = float(res.pvalue)
                else:
                    mx, my = float(np.mean(arr_x)), float(np.mean(arr_y))
                    cov = float(np.sum((arr_x - mx) * (arr_y - my)))
                    denom = float(np.sqrt(np.sum((arr_x - mx) ** 2) * np.sum((arr_y - my) ** 2)))
                    r_val = cov / denom if denom > 0 else 0.0
                    df = n - 2
                    t_val = r_val * math.sqrt(df / (1.0 - r_val ** 2)) if abs(r_val) < 1.0 else 0.0
                    p_val = _t_pvalue(t_val, df)

                df = n - 2
                t_val = r_val * math.sqrt(df / max(1e-12, (1.0 - r_val ** 2))) if abs(r_val) < 1.0 else float("inf")

                # Intervalo de confiança 95% via transformada z de Fisher
                if abs(r_val) < 1.0 and n > 3:
                    z = math.atanh(r_val)
                    se_z = 1.0 / math.sqrt(n - 3)
                    z_crit = 1.95996
                    ci_lower = math.tanh(z - z_crit * se_z)
                    ci_upper = math.tanh(z + z_crit * se_z)
                else:
                    ci_lower, ci_upper = r_val, r_val

                rows.append({
                    "var1": v1,
                    "var2": v2,
                    "r": round(r_val, 4),
                    "t": round(t_val, 4) if not math.isinf(t_val) else None,
                    "df": df,
                    "p": round(p_val, 6),
                    "n": n,
                    "ci_lower": round(ci_lower, 4),
                    "ci_upper": round(ci_upper, 4),
                })

        fields = [
            _build_field("var1", "Variável 1", "string"),
            _build_field("var2", "Variável 2", "string"),
            _build_field("r", "r de Pearson", "number", "dp:3"),
            _build_field("t", "t", "number", "dp:3"),
            _build_field("df", "gl", "integer"),
            _build_field("p", "p", "pvalue", "dp:3;p:.001"),
            _build_field("n", "N", "integer"),
            _build_field("ci_lower", "IC 95%: inferior", "number", "dp:3"),
            _build_field("ci_upper", "IC 95%: superior", "number", "dp:3"),
        ]

        notes = [
            {
                "symbol": "<em>Nota.</em>",
                "text": "Correlação de Pearson bicaudal com intervalo de confiança de 95% baseado na transformada de Fisher.",
            }
        ]

        table = _build_apa_table("Tabela de Correlação de Pearson", fields, rows, notes)
        return {
            "status": "complete",
            "results": {
                ".meta": [{"name": "correlation", "type": "table", "title": "Correlação de Pearson"}],
                "correlation": table,
            },
        }
