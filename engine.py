"""
Insight Flow Engine — by Aadhya
Full analysis engine. Returns a single JSON-serializable dict.
Handles 1L+ rows via chunked sampling where needed.

Key Features:
  - Comprehensive Data Cleaning: Automated handling of duplicates, nulls, data types, and outliers.
  - Automated Column Detection: Intelligently identifies date, metric, and customer columns.
  - Domain-Specific Analysis: Auto-detects business domain (Sales, Marketing, Finance, etc.) for tailored insights.
  - Anomaly Detection: Flags statistical outliers, significant period drops, and high null rates.
  - AI-Powered Summaries: Generates plain-language narratives for key findings and alerts.
  - Interactive HTML Reports: Produces a self-contained, shareable HTML report with all analyses and charts.
  - Diverse Analytical Modules: Includes KPI, RFM, Cohort, Funnel, Trend, Pareto, Price Sensitivity, Growth Accounting, Contribution Margin, Velocity, and Period Comparison.

Fixes applied:
  1. Nested f-strings replaced with pre-computed variables (Python < 3.12 safe)
  2. Column names synced after cleaning (_clean_col_name helper)
  3. pandas resample compatibility shim ("ME"/"QE" vs "M"/"Q")
  4. infer_datetime_format removed (deprecated in pandas 2.0+)
  5. RFM qcut replaced with rank-based scoring (avoids duplicate-bin crashes)
  6. seaborn import removed (unused dependency)
  7. ThreadPoolExecutor-safe (no shared mutable state)
  8. scipy removed — linear regression now uses numpy.polyfit (no extra dependency)
  9. plt.close(fig) guaranteed in _fig_to_b64 — zero memory leaks
"""

import io, json, base64, warnings, re, logging
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
from datetime import datetime
from collections import Counter
from typing import List, Optional

warnings.filterwarnings("ignore")
# ── Pandas resample compatibility shim ───────────────────────────────────────
# pandas >= 2.2 uses "ME" / "QE"; older versions use "M" / "Q"
try:
    pd.Series(range(4), index=pd.date_range("2020-01-01", periods=4, freq="ME")).resample("ME").sum()
    _RESAMPLE_MONTH   = "ME"
    _RESAMPLE_QUARTER = "QE"
except Exception:
    # Fallback for pandas < 2.2
    _RESAMPLE_MONTH   = "M"
    _RESAMPLE_QUARTER = "Q"

# ── Column-name cleaning helper ───────────────────────────────────────────────
def _clean_col_name(name: str) -> Optional[str]:
    """Apply the same transformation that _clean() applies to DataFrame columns."""
    if not name:
        return None
    name = name.strip().lower()
    name = re.sub(r"[\s\-/]+", "_", name)
    name = re.sub(r"[^\w]", "", name)
    return name or None


_DATE_COLUMN_TOKENS = {
    "date", "time", "dt", "datetime", "timestamp", "created", "updated",
    "period", "day", "week", "month", "year"
}


def _looks_like_date_column(name: str) -> bool:
    cleaned = _clean_col_name(str(name)) or ""
    tokens = {token for token in cleaned.split("_") if token}
    if tokens & _DATE_COLUMN_TOKENS:
        return True
    return cleaned.endswith(("date", "datetime", "timestamp"))


def _parse_datetime_candidate(series: pd.Series, column_name: str) -> Optional[pd.Series]:
    """Return parsed datetimes only for real date-like columns."""
    try:
        if pd.api.types.is_datetime64_any_dtype(series):
            return series
        if not _looks_like_date_column(column_name):
            return None

        non_null = series.dropna()
        if non_null.empty:
            return None

        cleaned_name = _clean_col_name(str(column_name)) or ""
        if pd.api.types.is_numeric_dtype(series):
            if cleaned_name != "year":
                return None
            years = pd.to_numeric(non_null, errors="coerce")
            if years.between(1900, 2100).mean() <= 0.8:
                return None
            parsed = pd.to_datetime(series.astype("Int64").astype(str), format="%Y", errors="coerce")
        else:
            sample = non_null.astype(str).str.strip()
            if sample.str.fullmatch(r"\d+(\.\d+)?").mean() > 0.9 and cleaned_name != "year":
                return None
            parsed = pd.to_datetime(series, errors="coerce")

        valid = parsed.notna()
        if valid.mean() <= 0.5:
            return None
        years = parsed[valid].dt.year
        if years.between(1900, 2100).mean() <= 0.8:
            return None
        return parsed
    except Exception:
        return None


# ── matplotlib defaults ───────────────────────────────────────────────────────
plt.rcParams.update({
    "figure.facecolor":  "#0d0d1a",
    "axes.facecolor":    "#0d0d1a",
    "axes.edgecolor":    "#1e1e35",
    "axes.labelcolor":   "#9090b8",
    "xtick.color":       "#9090b8",
    "ytick.color":       "#9090b8",
    "text.color":        "#e8e8f5",
    "grid.color":        "#1e1e35",
    "grid.linewidth":    0.5,
    "font.family":       "DejaVu Sans",
    "axes.spines.top":   False,
    "axes.spines.right": False,
})

ACCENT = "#7c6fff"
GREEN  = "#3de8b0"
RED    = "#ff5f7e"
YELLOW = "#ffc947"
PURPLE = "#b06fff"
BLUE   = "#38c6f8"
ORANGE = "#ff8c42"
TEAL   = "#00d4aa"

PALETTE = [ACCENT, GREEN, YELLOW, RED, PURPLE, BLUE, ORANGE, TEAL]


def _add_labels(ax, bars, fmt="{:.1f}", color="#e8e8f5", fontsize=8):
    """Add data labels on bar charts."""
    for bar in bars:
        val = bar.get_height() if hasattr(bar, "get_height") else bar.get_width()
        try:
            label = fmt.format(float(val))
        except Exception:
            continue
        if abs(float(val)) < 1e-9:
            continue
        if hasattr(bar, "get_height"):
            x = bar.get_x() + bar.get_width() / 2
            y = bar.get_height()
            ax.text(x, y + abs(y) * 0.02, label, ha="center", va="bottom",
                    fontsize=fontsize, color=color, fontweight="600")
        else:
            x = bar.get_width()
            y = bar.get_y() + bar.get_height() / 2
            ax.text(x + abs(x) * 0.01, y, label, ha="left", va="center",
                    fontsize=fontsize, color=color, fontweight="600")


class InsightFlowEngine:

    SAMPLE_THRESHOLD = 50_000
    MAX_CHART_ROWS   = 50_000

    def __init__(self, file_bytes: bytes, ext: str,
                 analysis_type: str = "kpi",
                 date_col=None, metric_col=None, customer_col=None):
        # Initialize logger for this instance
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.file_bytes    = file_bytes
        self.ext           = ext.lower()
        self.analysis_type = analysis_type.lower()
        self.date_col      = date_col
        self.metric_col    = metric_col
        self.customer_col  = customer_col
        self.df            = None
        self.df_sample     = None
        self.result        = {}
        self.audit         = []
        self.domain        = "General"

    # Define available analysis types that can be selected as the primary analysis.
    # These are *in addition* to the baseline KPI and Anomaly Detection.
    # The keys are the user-facing analysis_type strings.
    # The values are the corresponding internal methods to be called.
    _OPTIONAL_ANALYSIS_DISPATCH_MAP = {
        "rfm":          "_build_rfm",
        "cohort":       "_build_cohort",
        "funnel":       "_build_funnel",
        "ops":          "_build_ops",
        "seasonal":     "_build_seasonal",
        "trend":        "_build_trend",
        "pareto":       "_build_pareto",
        "price":        "_build_price_sensitivity",
        "growth":       "_build_growth_accounting",
        "contribution": "_build_contribution_margin",
        "velocity":     "_build_velocity",
        "period":       "_build_period_comparison",
    }

    # ── Public ────────────────────────────────────────────────────────────────

    def run(self) -> dict:
        self._load()
        self._clean()          # also syncs user-specified column names
        self._auto_detect()
        self._detect_domain()
        self._sample_if_large()
        self._build_preview()
        self._build_quality()
        self._build_kpi()
        self._build_anomalies()

        # Dynamically dispatch to the selected primary analysis type,
        # but only if it's one of the optional ones (not 'kpi', as it's already run).
        if self.analysis_type in self._OPTIONAL_ANALYSIS_DISPATCH_MAP:
            method_name = self._OPTIONAL_ANALYSIS_DISPATCH_MAP[self.analysis_type]
            fn = getattr(self, method_name, None)
            if fn:
                fn()
            else:
                self.logger.warning(f"Analysis type '{self.analysis_type}' has no corresponding method '{method_name}'. This should not happen if _OPTIONAL_ANALYSIS_DISPATCH_MAP is correct.")
        elif self.analysis_type != "kpi": # Log if an unknown or non-optional type was requested
            self.logger.warning(f"Unknown or non-optional analysis type requested: '{self.analysis_type}'. No specific analysis method dispatched.")

        self._build_ai_summary()
        self._build_report_html()
        self.result["audit"]         = self.audit
        self.result["analysis_type"] = self.analysis_type
        self.result["domain"]        = self.domain
        self.result["date_col"]      = self.date_col
        self.result["metric_col"]    = self.metric_col
        return self.result

    # ── Load ──────────────────────────────────────────────────────────────────

    def _load(self):
        # FIX: Read directly from in-memory bytes — never touches disk
        buf = io.BytesIO(self.file_bytes)
        if self.ext == ".csv":
            self.df = pd.read_csv(buf, low_memory=False)
        elif self.ext in (".xlsx", ".xls"):
            self.df = pd.read_excel(buf)
        elif self.ext == ".json":
            self.df = pd.read_json(buf)
        else:
            self.logger.error(f"Unsupported file type: {self.ext}")
            raise ValueError(f"Unsupported file type: {self.ext}")

    # ── Clean ─────────────────────────────────────────────────────────────────

    # Consider breaking this long function into smaller, more focused helper methods for readability and maintainability.
    def _clean(self):
        df = self.df
        before_rows  = len(df)
        before_nulls = int(df.isnull().sum().sum())
        before_dupes = int(df.duplicated().sum())

        df = df.drop_duplicates()
        for c in df.select_dtypes("object").columns:
            df[c] = df[c].str.strip()

        # Standardise column names
        df.columns = (
            df.columns.str.strip().str.lower()
            .str.replace(r"[\s\-/]+", "_", regex=True)
            .str.replace(r"[^\w]", "", regex=True)
        )

        # ── Sync user-specified column names with cleaned DataFrame columns ──
        if self.date_col:
            cleaned = _clean_col_name(self.date_col)
            self.date_col = cleaned if cleaned in df.columns else None

        if self.metric_col:
            cleaned = _clean_col_name(self.metric_col)
            self.metric_col = cleaned if cleaned in df.columns else None

        if self.customer_col:
            cleaned = _clean_col_name(self.customer_col)
            self.customer_col = cleaned if cleaned in df.columns else None
        # ─────────────────────────────────────────────────────────────────────

        drop_cols = df.columns[df.isnull().mean() > 0.90].tolist()
        df = df.drop(columns=drop_cols)

        for c in df.select_dtypes("number").columns:
            if df[c].isnull().any():
                df[c] = df[c].fillna(df[c].median())

        for c in df.select_dtypes("object").columns:
            if df[c].isnull().any():
                df[c] = df[c].fillna("Unknown")

        for c in df.select_dtypes("object").columns:
            parsed = _parse_datetime_candidate(df[c], c)
            if parsed is not None:
                df[c] = parsed

        for c in df.select_dtypes("object").columns:
            sample = df[c].dropna().head(50).astype(str)
            if sample.str.contains(r"[\$£₹,]", regex=True).any():
                cleaned   = df[c].astype(str).str.replace(r"[\$£₹,\s]", "", regex=True)
                converted = pd.to_numeric(cleaned, errors="coerce")
                if converted.notna().sum() > len(df) * 0.5:
                    df[c] = converted

        for c in df.select_dtypes("number").columns:
            q1, q3 = df[c].quantile(0.25), df[c].quantile(0.75)
            iqr = q3 - q1
            mask = (df[c] < q1 - 3*iqr) | (df[c] > q3 + 3*iqr)
            if mask.any():
                df[f"{c}_outlier"] = mask.astype(int)

        key_cols = [c for c in df.columns if any(k in c.lower() for k in ["id","key","uid","ref"])]
        if key_cols:
            df = df.drop_duplicates(subset=key_cols, keep="first")

        self.df = df
        after_rows  = len(df)
        after_nulls = int(df.isnull().sum().sum())

        score = 100
        null_pct = before_nulls / max(before_rows * len(df.columns), 1)
        dupe_pct = before_dupes / max(before_rows, 1)
        score -= min(null_pct * 100 * 0.4, 30)
        score -= min(dupe_pct * 100 * 0.3, 20)

        self.result["quality_scorecard"] = {
            "rows_before":   before_rows,
            "rows_after":    after_rows,
            "cols":          len(df.columns),
            "nulls_before":  before_nulls,
            "nulls_after":   after_nulls,
            "dupes_removed": before_dupes,
            "quality_score": round(max(score, 0), 1),
            "dropped_cols":  drop_cols,
        }
        self.audit.append(
            f"Cleaned: {before_rows - after_rows} rows removed, "
            f"{before_nulls - after_nulls} nulls fixed"
        )

    # ── Domain Detection ──────────────────────────────────────────────────────

    def _detect_domain(self):
        cols = " ".join(self.df.columns.tolist()).lower()
        domains = {
            "Sales":      ["revenue","sales","order","deal","quota","pipeline","invoice","discount","product","sku","unit_price"],
            "Marketing":  ["campaign","ctr","impression","click","conversion","lead","mql","sql","channel","source","utm","spend","roas","cpc"],
            "Finance":    ["profit","margin","cost","expense","budget","forecast","cash","ebitda","opex","capex","balance","asset","liability"],
            "HR":         ["employee","headcount","attrition","salary","tenure","hire","departure","department","role","team","engagement"],
            "Operations": ["ticket","sla","handle_time","utilization","queue","backlog","throughput","ops","incident","resolution"],
            "E-commerce": ["cart","checkout","basket","refund","return","sku","category","rating","review","shipping"],
        }
        scores = {domain: sum(1 for kw in keywords if kw in cols)
                  for domain, keywords in domains.items()}
        best = max(scores, key=scores.get)
        self.domain = best if scores[best] >= 2 else "General"
        self.result["domain"] = self.domain

    # ── Auto Detect ───────────────────────────────────────────────────────────

    def _auto_detect(self):
        df = self.df

        if not self.date_col:
            for c in df.columns:
                parsed = _parse_datetime_candidate(df[c], c)
                if parsed is not None:
                    df[c] = parsed
                    self.date_col = c
                    break

        if not self.metric_col:
            num_cols = df.select_dtypes("number").columns.tolist()
            rev_kw = ["revenue","sales","amount","value","price","spend","gmv","mrr","arr",
                      "total","profit","income"]
            for c in num_cols:
                if any(k in c.lower() for k in rev_kw):
                    self.metric_col = c; break
            if not self.metric_col:
                clean_num = [c for c in num_cols if not c.endswith(("_outlier","_pct_rank"))]
                if clean_num:
                    self.metric_col = clean_num[0]

        if not self.customer_col:
            id_kw = ["customer","user","client","member","id"]
            for c in df.columns:
                if any(k in c.lower() for k in id_kw):
                    self.customer_col = c; break

        self.result["detected"] = {
            "date_col":     self.date_col,
            "metric_col":   self.metric_col,
            "customer_col": self.customer_col,
            "total_rows":   len(df),
            "total_cols":   len(df.columns),
            "columns":      list(df.columns),
        }

    def _sample_if_large(self):
        if len(self.df) > self.MAX_CHART_ROWS:
            self.df_sample = self.df.sample(self.MAX_CHART_ROWS, random_state=42)
            self.audit.append(f"Large file: sampled {self.MAX_CHART_ROWS:,} rows for charts")
        else:
            self.df_sample = self.df

    # ── Preview ───────────────────────────────────────────────────────────────

    def _build_preview(self):
        df = self.df
        preview = df.head(10).copy()
        for c in preview.select_dtypes("datetime64").columns:
            preview[c] = preview[c].astype(str)
        self.result["preview"] = {
            "columns": list(preview.columns),
            "rows":    preview.fillna("").values.tolist(),
        }

    # ── Quality ───────────────────────────────────────────────────────────────

    def _build_quality(self):
        df = self.df
        col_stats = []
        for c in df.columns:
            if c.endswith("_outlier"):
                continue
            null_count = int(df[c].isnull().sum())
            fill_rate  = round((1 - null_count / len(df)) * 100, 1)
            col_stats.append({
                "col":        c,
                "dtype":      str(df[c].dtype),
                "null_count": null_count,
                "fill_rate":  fill_rate,
                "unique":     int(df[c].nunique()),
            })
        self.result["col_stats"] = col_stats

    # ── KPI ───────────────────────────────────────────────────────────────────

    def _build_kpi(self):
        if not self.date_col or not self.metric_col:
            self.result["kpi"] = {"error": "No date or metric column detected"}
            return

        df = self.df[[self.date_col, self.metric_col]].dropna().copy()
        df = df.sort_values(self.date_col)
        df.set_index(self.date_col, inplace=True)

        monthly   = df[self.metric_col].resample(_RESAMPLE_MONTH).sum().reset_index()
        monthly.columns = ["period", "value"]
        monthly["mom_pct"] = monthly["value"].pct_change() * 100
        monthly["yoy_pct"] = (
            (monthly["value"] - monthly["value"].shift(12))
            / monthly["value"].shift(12).abs() * 100
        )

        quarterly = df[self.metric_col].resample(_RESAMPLE_QUARTER).sum().reset_index()
        quarterly.columns = ["period", "value"]
        quarterly["qoq_pct"] = quarterly["value"].pct_change() * 100

        total   = float(monthly["value"].sum())
        avg_mom = float(monthly["mom_pct"].mean())
        best_m  = monthly.loc[monthly["value"].idxmax()]
        worst_m = monthly.loc[monthly["value"].idxmin()]

        self.result["kpi"] = {
            "summary": {
                "total":       round(total, 2),
                "avg_monthly": round(float(monthly["value"].mean()), 2),
                "avg_mom_pct": round(avg_mom, 2),
                "best_month":  {"period": str(best_m["period"])[:7],  "value": round(float(best_m["value"]), 2)},
                "worst_month": {"period": str(worst_m["period"])[:7], "value": round(float(worst_m["value"]), 2)},
                "months":      len(monthly),
            },
            "monthly":   self._df_to_json(monthly),
            "quarterly": self._df_to_json(quarterly),
            "charts": {
                "trend":  self._chart_kpi_trend(monthly),
                "growth": self._chart_growth_bars(monthly),
                "qoq":    self._chart_qoq(quarterly),
                "box":    self._chart_kpi_box(df, self.metric_col),
            }
        }

    def _chart_kpi_trend(self, monthly):
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(monthly["period"], monthly["value"], color=ACCENT, linewidth=2.5, zorder=3)
        ax.fill_between(monthly["period"], monthly["value"], alpha=0.15, color=ACCENT)
        ax.scatter(monthly["period"], monthly["value"], color=ACCENT, s=40, zorder=4)
        step = max(1, len(monthly) // 8)
        for i, (p, v) in enumerate(zip(monthly["period"], monthly["value"])):
            if i % step == 0:
                ax.text(p, v * 1.02, f"{v:,.0f}", ha="center", va="bottom",
                        fontsize=7, color="#e8e8f5", fontweight="600")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.set_title(f"Monthly {self.metric_col.replace('_',' ').title()}", fontsize=12, pad=10)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    def _chart_growth_bars(self, monthly):
        fig, ax = plt.subplots(figsize=(11, 3.5))
        vals   = monthly["mom_pct"].fillna(0)
        colors = [GREEN if v >= 0 else RED for v in vals]
        bars   = ax.bar(monthly["period"], vals, color=colors, width=20, alpha=0.85)
        _add_labels(ax, bars, fmt="{:.1f}%", fontsize=7)
        ax.axhline(0, color="#ffffff30", linewidth=0.8)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))
        ax.set_title("Month-over-Month Growth (%)", fontsize=12, pad=10)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    def _chart_qoq(self, quarterly):
        fig, ax = plt.subplots(figsize=(8, 3.5))
        labels = [str(p)[:7] for p in quarterly["period"]]
        vals   = quarterly["qoq_pct"].fillna(0)
        colors = [GREEN if v >= 0 else RED for v in vals]
        bars   = ax.bar(range(len(labels)), vals, color=colors, alpha=0.85)
        _add_labels(ax, bars, fmt="{:.1f}%", fontsize=7)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.axhline(0, color="#ffffff30", linewidth=0.8)
        ax.set_title("Quarter-over-Quarter Growth (%)", fontsize=12, pad=10)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    def _chart_kpi_box(self, df_indexed, metric_col):
        fig, ax = plt.subplots(figsize=(6, 4))
        data = df_indexed[metric_col].dropna()
        ax.boxplot(data, vert=True, patch_artist=True,
                   boxprops=dict(facecolor=ACCENT+"44", color=ACCENT),
                   medianprops=dict(color=GREEN, linewidth=2),
                   whiskerprops=dict(color="#9090b8"),
                   capprops=dict(color="#9090b8"),
                   flierprops=dict(marker="o", color=RED, alpha=0.4, markersize=3))
        med = float(data.median())
        ax.text(1.15, med, f"Median: {med:,.1f}", va="center", fontsize=8, color=GREEN)
        ax.set_title(f"{metric_col.replace('_',' ').title()} Distribution", fontsize=11, pad=10)
        ax.set_xticklabels([metric_col.replace("_", " ").title()])
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Anomaly Detection ─────────────────────────────────────────────────────

    def _build_anomalies(self):
        df     = self.df_sample
        alerts = []
        num_cols = [c for c in df.select_dtypes("number").columns
                    if not c.endswith(("_outlier","_pct_rank"))]

        for col in num_cols[:20]:
            series = df[col].dropna()
            if len(series) < 10:
                continue
            mean, std = series.mean(), series.std()
            if std == 0:
                continue
            z_scores  = np.abs((series - mean) / std)
            anomalies = z_scores[z_scores > 2.5]
            for idx in anomalies.index[:3]:
                val       = df.at[idx, col]
                z         = float(z_scores[idx])
                pct_dev   = ((val - mean) / mean * 100) if mean != 0 else 0
                direction = "above" if val > mean else "below"
                alerts.append({
                    "severity":    "CRITICAL" if z > 3.75 else "WARNING",
                    "column":      col,
                    "value":       round(float(val), 3),
                    "z_score":     round(z, 2),
                    "description": (
                        f"{col.replace('_',' ').title()} is {abs(pct_dev):.1f}% {direction} "
                        f"average (z={z:.2f}). Value: {val:,.2f}, Mean: {mean:,.2f}"
                    ),
                    "type": "Z-Score Anomaly",
                })

        # Period Drop Anomaly Detection
        if self.date_col and self.metric_col:
            try:
                ts     = (self.df[[self.date_col, self.metric_col]]
                          .dropna().sort_values(self.date_col)
                          .set_index(self.date_col)[self.metric_col]
                          .resample(_RESAMPLE_MONTH).sum())
                pct_ch = ts.pct_change()
                for idx in pct_ch[pct_ch < -0.20].index:
                    drop = float(pct_ch[idx]) * 100
                    loc  = ts.index.get_loc(idx)
                    prev = float(ts.iloc[loc - 1]) if loc > 0 else 0
                    curr = float(ts[idx])
                    alerts.append({
                        "severity":    "CRITICAL" if drop < -0.40 else "WARNING",
                        "column":      self.metric_col,
                        "value":       round(curr, 2),
                        "z_score":     None,
                        "description": (
                            f"{self.metric_col.replace('_',' ').title()} dropped "
                            f"{abs(drop):.1f}% in {str(idx)[:7]} "
                            f"({prev:,.2f} → {curr:,.2f}). Needs attention."
                        ),
                        "type": "Period Drop",
                    })
            except Exception as e:
                self.logger.warning(f"Error detecting period drop anomalies for metric '{self.metric_col}': {e}")
                # Continue with other anomaly checks even if this one fails

        for col in self.df.columns:
            null_pct = self.df[col].isnull().mean()
            if null_pct > 0.20:
                alerts.append({
                    "severity":    "WARNING",
                    "column":      col,
                    "value":       round(null_pct * 100, 1),
                    "z_score":     None,
                    "description": (
                        f"Column '{col}' has {null_pct*100:.1f}% missing values. "
                        f"Data pipeline issue likely."
                    ),
                    "type": "High Null Rate",
                })

        alerts.sort(key=lambda a: 0 if a["severity"] == "CRITICAL" else 1)
        chart = self._chart_alerts(alerts) if alerts else None
        self.result["anomalies"] = {
            "total":    len(alerts),
            "critical": sum(1 for a in alerts if a["severity"] == "CRITICAL"),
            "warnings": sum(1 for a in alerts if a["severity"] == "WARNING"),
            "alerts":   alerts[:30],
            "chart":    chart,
        }

    def _chart_alerts(self, alerts):
        types = Counter(a["type"] for a in alerts)
        if not types:
            return None
        fig, ax = plt.subplots(figsize=(7, 3.5))
        colors_map = {"Z-Score Anomaly": ACCENT, "Period Drop": RED, "High Null Rate": YELLOW}
        bars = ax.barh(list(types.keys()), list(types.values()),
                       color=[colors_map.get(k, BLUE) for k in types.keys()], alpha=0.85)
        for bar in bars:
            val = bar.get_width()
            ax.text(val + 0.1, bar.get_y() + bar.get_height()/2,
                    str(int(val)), va="center", fontsize=9, color="#e8e8f5", fontweight="600")
        ax.set_title("Alert Summary by Type", fontsize=12, pad=10)
        ax.invert_yaxis()
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── RFM ───────────────────────────────────────────────────────────────────

    def _build_rfm(self):
        if not self.customer_col or not self.date_col or not self.metric_col:
            self.result["rfm"] = {"error": "RFM needs customer, date, and value columns"}
            return
        try:
            df       = self.df[[self.customer_col, self.date_col, self.metric_col]].dropna().copy()
            snapshot = df[self.date_col].max() + pd.Timedelta(days=1)
            rfm      = df.groupby(self.customer_col).agg(
                Recency  =(self.date_col,   lambda x: (snapshot - x.max()).days),
                Frequency=(self.date_col,   "count"),
                Monetary =(self.metric_col, "sum"),
            ).reset_index()

            # ── Use rank-based scoring instead of qcut to avoid duplicate-bin errors ──
            def _rank_score(series, ascending=True):
                """Score 1-5 using percentile ranks; robust to many duplicates."""
                pct = series.rank(pct=True, method="average")
                if ascending:
                    return pd.cut(pct, bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
                                  labels=[1, 2, 3, 4, 5], include_lowest=True).astype(float)
                else:
                    return pd.cut(pct, bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0],
                                  labels=[5, 4, 3, 2, 1], include_lowest=True).astype(float)

            rfm["R_score"] = _rank_score(rfm["Recency"],   ascending=False)
            rfm["F_score"] = _rank_score(rfm["Frequency"], ascending=True)
            rfm["M_score"] = _rank_score(rfm["Monetary"],  ascending=True)
            rfm["RFM_score"] = rfm["R_score"] + rfm["F_score"] + rfm["M_score"]

            def segment(s):
                if s >= 13:  return "Champions"
                elif s >= 10: return "Loyal"
                elif s >= 7:  return "At Risk"
                elif s >= 4:  return "Needs Attention"
                else:         return "Lost"

            rfm["Segment"] = rfm["RFM_score"].apply(segment)

            seg_summary = rfm.groupby("Segment").agg(
                Count   =("RFM_score","count"),
                Avg_Rec =("Recency","mean"),
                Avg_Freq=("Frequency","mean"),
                Avg_Mon =("Monetary","mean"),
            ).round(1).reset_index()

            self.result["rfm"] = {
                "segments":        seg_summary.to_dict("records"),
                "total_customers": len(rfm),
                "charts": {
                    "pie":     self._chart_rfm_donut(rfm),
                    "scatter": self._chart_rfm_scatter(rfm),
                    "bar":     self._chart_rfm_bar(seg_summary),
                },
                "sample": rfm.head(100).fillna(0).round(2).to_dict("records"),
            }
        except Exception as e:
            self.logger.exception(f"RFM analysis failed for customer_col='{self.customer_col}', date_col='{self.date_col}', metric_col='{self.metric_col}'")
            self.result["rfm"] = {"error": str(e)}

    def _chart_rfm_donut(self, rfm):
        seg_counts = rfm["Segment"].value_counts()
        colors = [ACCENT, GREEN, YELLOW, RED, PURPLE]
        fig, ax = plt.subplots(figsize=(6, 5))
        wedges, texts, autotexts = ax.pie(
            seg_counts.values, labels=seg_counts.index,
            autopct="%1.1f%%", colors=colors[:len(seg_counts)],
            startangle=140, pctdistance=0.75,
            wedgeprops=dict(width=0.55),
        )
        for t in texts:     t.set_color("#e8e8f5"); t.set_fontsize(9)
        for t in autotexts: t.set_color("#0d0d1a"); t.set_fontweight("bold"); t.set_fontsize(8)
        ax.set_title("Customer Segments (RFM)", fontsize=12, pad=10)
        ax.text(0, 0, f"{len(rfm):,}\nCustomers", ha="center", va="center",
                fontsize=10, color="#e8e8f5", fontweight="bold")
        fig.tight_layout()
        return self._fig_to_b64(fig)

    def _chart_rfm_scatter(self, rfm):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        sc = ax.scatter(rfm["Recency"], rfm["Monetary"],
                        c=rfm["RFM_score"], cmap="plasma",
                        alpha=0.5, s=15, vmin=3, vmax=15)
        plt.colorbar(sc, ax=ax, label="RFM Score")
        ax.set_xlabel("Recency (days)")
        ax.set_ylabel("Monetary Value")
        ax.set_title("Recency vs Monetary Value", fontsize=12, pad=10)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    def _chart_rfm_bar(self, seg_summary):
        fig, ax = plt.subplots(figsize=(7, 4))
        seg_colors = {"Champions": GREEN, "Loyal": ACCENT, "At Risk": YELLOW,
                      "Needs Attention": ORANGE, "Lost": RED}
        colors = [seg_colors.get(s, BLUE) for s in seg_summary["Segment"]]
        bars   = ax.barh(seg_summary["Segment"], seg_summary["Count"], color=colors, alpha=0.85)
        for bar in bars:
            val = bar.get_width()
            ax.text(val + 0.5, bar.get_y() + bar.get_height()/2,
                    f"{int(val):,}", va="center", fontsize=9, color="#e8e8f5", fontweight="600")
        ax.set_title("Customers per Segment", fontsize=12, pad=10)
        ax.invert_yaxis()
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Cohort ────────────────────────────────────────────────────────────────

    def _build_cohort(self):
        df        = self.df_sample
        date_cols = df.select_dtypes("datetime64").columns.tolist()
        if not date_cols:
            self.result["cohort"] = {"error": "Cohort needs at least one date column"}
            return
        try:
            df = df.copy()
            df["cohort_month"] = df[date_cols[0]].dt.to_period("M")
            if self.metric_col:
                aov = df.groupby("cohort_month")[self.metric_col].agg(
                    AOV="mean", Total="sum", Count="count"
                ).round(2).reset_index()
                aov["cohort_month"] = aov["cohort_month"].astype(str)
                self.result["cohort"] = {
                    "data":  aov.to_dict("records"),
                    "chart": self._chart_cohort_aov(aov),
                }
            else:
                self.result["cohort"] = {"error": "No metric column for cohort AOV"}
        except Exception as e:
            self.logger.exception(f"Cohort analysis failed for date_cols='{date_cols}' and metric_col='{self.metric_col}'")
            self.result["cohort"] = {"error": str(e)}

    def _chart_cohort_aov(self, aov):
        fig, ax = plt.subplots(figsize=(11, 4))
        bars = ax.bar(aov["cohort_month"], aov["AOV"], color=ACCENT, alpha=0.8)
        _add_labels(ax, bars, fmt="{:.0f}", fontsize=7)
        ax.plot(aov["cohort_month"], aov["AOV"], color=GREEN, linewidth=1.5,
                marker="o", markersize=3, zorder=5)
        ax.set_title("Average Order Value per Cohort Month", fontsize=12, pad=10)
        ax.set_xlabel("Cohort Month")
        ax.set_ylabel("AOV")
        plt.xticks(rotation=45, ha="right", fontsize=7)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Funnel ────────────────────────────────────────────────────────────────

    def _build_funnel(self):
        df        = self.df
        stage_col = None
        for c in df.select_dtypes("object").columns:
            if any(k in c.lower() for k in ["stage","step","status","phase","funnel"]):
                stage_col = c; break
        if not stage_col:
            for c in df.select_dtypes("object").columns:
                if 2 <= df[c].nunique() <= 12:
                    stage_col = c; break
        if not stage_col:
            self.result["funnel"] = {"error": "No stage column found"}
            return
        counts = df[stage_col].value_counts().reset_index()
        counts.columns = ["stage", "count"]
        counts["conv_pct"] = (counts["count"] / counts["count"].iloc[0] * 100).round(1)
        self.result["funnel"] = {
            "data":      counts.to_dict("records"),
            "chart":     self._chart_funnel(counts),
            "stage_col": stage_col,
        }

    # Consider breaking this long function into smaller, more focused helper methods.
    def _chart_funnel(self, counts):
        fig, ax = plt.subplots(figsize=(9, 5))
        colors = PALETTE[:len(counts)]
        bars   = ax.barh(counts["stage"], counts["count"], color=colors, alpha=0.85)
        for bar, pct in zip(bars, counts["conv_pct"]):
            w = bar.get_width()
            ax.text(w + counts["count"].max() * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    f"{pct:.1f}%  ({int(w):,})", va="center", fontsize=9,
                    color="#e8e8f5", fontweight="600")
        ax.invert_yaxis()
        ax.set_title("Funnel Conversion Analysis", fontsize=12, pad=10)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Ops ───────────────────────────────────────────────────────────────────

    def _build_ops(self):
        if not self.date_col or not self.metric_col:
            self.result["ops"] = {"error": "Ops needs date and metric columns"}
            return
        df   = (self.df_sample[[self.date_col, self.metric_col]]
                .dropna().sort_values(self.date_col)
                .set_index(self.date_col)[self.metric_col])
        ma7  = df.rolling(7).mean()
        ma30 = df.rolling(30).mean()
        std7 = df.rolling(7).std()
        upper = ma7 + 2*std7
        lower = ma7 - 2*std7
        self.result["ops"] = {
            "chart": self._chart_ops(df, ma7, ma30, upper, lower),
            "summary": {
                "mean": round(float(df.mean()), 2),
                "std":  round(float(df.std()),  2),
                "max":  round(float(df.max()),  2),
                "min":  round(float(df.min()),  2),
            }
        }

    # Consider breaking this long function into smaller, more focused helper methods.
    def _chart_ops(self, series, ma7, ma30, upper, lower):
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(series.index, series, color="#94A3B8", linewidth=0.8, alpha=0.5, label="Actual")
        ax.plot(series.index, ma7,    color=ACCENT,   linewidth=2,   label="7-day MA")
        ax.plot(series.index, ma30,   color=GREEN,    linewidth=2,   label="30-day MA")
        ax.fill_between(series.index, lower, upper, alpha=0.08, color=ACCENT, label="Bollinger Band (±2σ)")
        ax.legend(fontsize=9)
        ax.set_title(f"Operational Trend — {self.metric_col}", fontsize=12, pad=10)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Seasonal ──────────────────────────────────────────────────────────────

    def _build_seasonal(self):
        if not self.date_col or not self.metric_col:
            self.result["seasonal"] = {"error": "Seasonal needs date and metric columns"}
            return
        df = self.df_sample[[self.date_col, self.metric_col]].dropna().copy()
        df["month"]   = df[self.date_col].dt.month
        df["quarter"] = df[self.date_col].dt.quarter
        df["year"]    = df[self.date_col].dt.year
        df["dow"]     = df[self.date_col].dt.dayofweek

        monthly_avg = df.groupby("month")[self.metric_col].mean()
        quarterly   = df.groupby("quarter")[self.metric_col].sum()
        yearly      = df.groupby("year")[self.metric_col].sum()
        dow_avg     = df.groupby("dow")[self.metric_col].mean()

        self.result["seasonal"] = {
            "chart":       self._chart_seasonal(monthly_avg, quarterly, yearly, dow_avg),
            "monthly_avg": {str(k): round(float(v), 2) for k, v in monthly_avg.items()},
            "quarterly_sum": {str(k): round(float(v), 2) for k, v in quarterly.items()},
        }

    # Consider breaking this long function into smaller, more focused helper methods.
    def _chart_seasonal(self, monthly, quarterly, yearly, dow_avg):
        month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        dow_names   = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        fig, axes   = plt.subplots(2, 2, figsize=(13, 8))
        fig.suptitle(f"Seasonal Patterns — {self.metric_col}", fontsize=13, y=1.01)

        vals = monthly.reindex(range(1,13)).fillna(0)
        b0   = axes[0,0].bar(range(1,13), vals, color=ACCENT, alpha=0.85)
        _add_labels(axes[0,0], b0, fmt="{:.0f}", fontsize=6)
        axes[0,0].set_xticks(range(1,13))
        axes[0,0].set_xticklabels(month_names, rotation=45, fontsize=7)
        axes[0,0].set_title("Average by Month")

        qvals = quarterly.reindex([1,2,3,4]).fillna(0)
        b1    = axes[0,1].bar([1,2,3,4], qvals, color=PURPLE, alpha=0.85)
        _add_labels(axes[0,1], b1, fmt="{:.0f}", fontsize=7)
        axes[0,1].set_xticks([1,2,3,4])
        axes[0,1].set_xticklabels(["Q1","Q2","Q3","Q4"])
        axes[0,1].set_title("Total by Quarter")

        axes[1,0].plot(yearly.index, yearly.values, marker="o", color=GREEN, linewidth=2)
        for x, y in zip(yearly.index, yearly.values):
            axes[1,0].text(x, y * 1.02, f"{y:,.0f}", ha="center", va="bottom", fontsize=7, color=GREEN)
        axes[1,0].set_title("Total by Year")

        dvals = dow_avg.reindex(range(7)).fillna(0)
        b3    = axes[1,1].bar(range(7), dvals, color=YELLOW, alpha=0.85)
        _add_labels(axes[1,1], b3, fmt="{:.0f}", fontsize=7)
        axes[1,1].set_xticks(range(7))
        axes[1,1].set_xticklabels(dow_names)
        axes[1,1].set_title("Average by Day of Week")

        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Trend Analysis ────────────────────────────────────────────────────────

    def _build_trend(self):
        if not self.date_col or not self.metric_col:
            self.result["trend"] = {"error": "Trend needs date and metric columns"}
            return
        try:
            df = (self.df[[self.date_col, self.metric_col]]
                  .dropna().sort_values(self.date_col)
                  .set_index(self.date_col))
            ts = df[self.metric_col].resample(_RESAMPLE_MONTH).sum()

            x    = np.arange(len(ts))
            y    = ts.values.astype(float)

            # FIX: numpy polyfit replaces scipy.stats.linregress — no extra dependency
            coeffs     = np.polyfit(x, y, 1)          # [slope, intercept]
            slope      = float(coeffs[0])
            intercept  = float(coeffs[1])
            trend_line = slope * x + intercept

            # Pearson r via numpy corrcoef
            if y.std() > 0:
                r = float(np.corrcoef(x, y)[0, 1])
            else:
                r = 0.0

            ma3  = ts.rolling(3).mean()
            ma6  = ts.rolling(6).mean()

            direction = "upward" if slope > 0 else "downward"
            strength  = "strong" if abs(r) > 0.7 else ("moderate" if abs(r) > 0.4 else "weak")

            self.result["trend"] = {
                "chart":     self._chart_trend(ts, trend_line, ma3, ma6),
                "slope":     round(slope, 3),
                "r_squared": round(r**2, 3),
                "direction": direction,
                "strength":  strength,
                "summary":   (
                    f"The metric shows a {strength} {direction} trend (R²={r**2:.2f}). "
                    f"Average monthly change: {slope:+,.2f}."
                ),
            }
        except Exception as e:
            self.logger.exception(f"Trend analysis failed for date_col='{self.date_col}', metric_col='{self.metric_col}'")
            self.result["trend"] = {"error": str(e)}

    def _chart_trend(self, ts, trend_line, ma3, ma6):
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.bar(ts.index, ts.values, color=ACCENT, alpha=0.35, width=25, label="Monthly Value")
        ax.plot(ts.index, trend_line, color=RED,    linewidth=2.5, linestyle="--", label="Linear Trend")
        ax.plot(ts.index, ma3,        color=GREEN,  linewidth=2,   label="3-Month MA")
        ax.plot(ts.index, ma6,        color=YELLOW, linewidth=2,   label="6-Month MA")
        ax.legend(fontsize=9)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.set_title(f"Trend Analysis — {self.metric_col.replace('_',' ').title()}", fontsize=12, pad=10)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Pareto ────────────────────────────────────────────────────────────────

    def _build_pareto(self):
        if not self.metric_col:
            self.result["pareto"] = {"error": "Pareto needs a metric column"}
            return
        try:
            df       = self.df
            cat_cols = df.select_dtypes("object").columns.tolist()
            group_col = next(
                (c for c in cat_cols if c not in [self.date_col, self.customer_col]), None
            )
            if not group_col and cat_cols:
                group_col = cat_cols[0]
            if not group_col:
                self.result["pareto"] = {"error": "No categorical column found for grouping"}
                return

            grouped = (df.groupby(group_col)[self.metric_col]
                       .sum().sort_values(ascending=False).reset_index())
            grouped.columns = ["category", "value"]
            grouped["cumulative_pct"]  = (grouped["value"].cumsum() / grouped["value"].sum() * 100).round(1)
            grouped["pct_of_total"]    = (grouped["value"] / grouped["value"].sum() * 100).round(1)
            threshold_idx = int((grouped["cumulative_pct"] <= 80).sum())

            self.result["pareto"] = {
                "chart":      self._chart_pareto(grouped, threshold_idx),
                "group_col":  group_col,
                "top_items":  threshold_idx,
                "data":       grouped.head(20).to_dict("records"),
                "summary":    (
                    f"Top {threshold_idx} {group_col} items drive 80% of "
                    f"total {self.metric_col}."
                ),
            }
        except Exception as e:
            self.logger.exception(f"Pareto analysis failed for metric_col='{self.metric_col}' and detected group_col='{group_col}'")
            self.result["pareto"] = {"error": str(e)}

    def _chart_pareto(self, data, threshold_idx):
        top = data.head(20)
        fig, ax1 = plt.subplots(figsize=(12, 5))
        ax2 = ax1.twinx()
        colors = [GREEN if i < threshold_idx else ACCENT for i in range(len(top))]
        ax1.bar(range(len(top)), top["value"], color=colors, alpha=0.8)
        ax2.plot(range(len(top)), top["cumulative_pct"], color=RED, linewidth=2.5,
                 marker="o", markersize=4, label="Cumulative %")
        ax2.axhline(80, color=YELLOW, linewidth=1.5, linestyle="--", alpha=0.7, label="80% line")
        ax2.set_ylabel("Cumulative %", color=RED)
        ax2.set_ylim(0, 115)
        ax1.set_xticks(range(len(top)))
        ax1.set_xticklabels(top["category"].astype(str), rotation=45, ha="right", fontsize=7)
        ax1.set_ylabel(self.metric_col)
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        green_patch = mpatches.Patch(color=GREEN, label="Top 80% contributors")
        ax2.legend(handles=[green_patch], loc="upper left", fontsize=8)
        ax1.set_title(f"Pareto Analysis — {self.metric_col.replace('_',' ').title()}", fontsize=12, pad=10)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Price Sensitivity ─────────────────────────────────────────────────────

    def _build_price_sensitivity(self):
        try:
            df       = self.df
            num_cols = df.select_dtypes("number").columns.tolist()
            price_col = next(
                (c for c in num_cols if any(k in c.lower() for k in ["price","cost","rate","fee","charge"])),
                None,
            )
            vol_col = next(
                (c for c in num_cols if any(k in c.lower() for k in ["quantity","volume","units","qty","count","orders"])
                 and c != price_col),
                None,
            )
            if not price_col or not vol_col:
                self.result["price"] = {"error": "Need price/cost and volume/quantity columns"}
                return

            data = df[[price_col, vol_col]].dropna()
            data = data[data[price_col] > 0].copy()
            data["price_bin"] = pd.qcut(data[price_col], q=10, duplicates="drop")
            grouped = data.groupby("price_bin", observed=True).agg(
                avg_price =(price_col, "mean"),
                avg_volume=(vol_col,   "mean"),
                count     =(vol_col,   "count"),
            ).reset_index()

            # FIX: Pearson r via numpy corrcoef — no scipy needed
            p_arr = data[price_col].values.astype(float)
            v_arr = data[vol_col].values.astype(float)
            if p_arr.std() > 0 and v_arr.std() > 0:
                corr = float(np.corrcoef(p_arr, v_arr)[0, 1])
            else:
                corr = 0.0

            self.result["price"] = {
                "chart":       self._chart_price_sensitivity(grouped, price_col, vol_col, corr),
                "price_col":   price_col,
                "volume_col":  vol_col,
                "correlation": round(corr, 3),
                "summary": (
                    f"Price-volume correlation: {corr:.2f}. "
                    + ("Higher price reduces demand (elastic)." if corr < -0.3
                       else "Weak price-volume relationship." if abs(corr) < 0.3
                       else "Higher price correlates with more volume (premium effect).")
                ),
            }
        except Exception as e:
            self.logger.exception(f"Price sensitivity analysis failed for price_col='{price_col}', vol_col='{vol_col}'")
            self.result["price"] = {"error": str(e)}

    def _chart_price_sensitivity(self, grouped, price_col, vol_col, corr):
        fig, ax1 = plt.subplots(figsize=(10, 5))
        ax2 = ax1.twinx()
        ax1.bar(range(len(grouped)), grouped["avg_volume"], color=ACCENT, alpha=0.7, label="Avg Volume")
        ax2.plot(range(len(grouped)), grouped["avg_price"], color=RED, linewidth=2.5,
                 marker="o", markersize=5, label="Avg Price")
        ax1.set_ylabel("Average Volume", color=ACCENT)
        ax2.set_ylabel("Average Price", color=RED)
        ax1.set_xticks(range(len(grouped)))
        ax1.set_xticklabels([f"P{i+1}" for i in range(len(grouped))], fontsize=8)
        ax1.set_title(f"Price Sensitivity — {price_col} vs {vol_col} (corr={corr:.2f})", fontsize=12, pad=10)
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1+lines2, labels1+labels2, fontsize=9)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Growth Accounting ─────────────────────────────────────────────────────

    def _build_growth_accounting(self):
        if not self.date_col or not self.customer_col or not self.metric_col:
            self.result["growth"] = {"error": "Growth accounting needs date, customer, and metric columns"}
            return
        try:
            df = self.df[[self.date_col, self.customer_col, self.metric_col]].dropna().copy()
            df["period"] = df[self.date_col].dt.to_period("M")

            monthly_custs = (df.groupby(["period", self.customer_col])[self.metric_col]
                             .sum().reset_index())
            periods = sorted(monthly_custs["period"].unique())

            records = []
            for i, p in enumerate(periods[1:], 1):
                prev_p  = periods[i-1]
                prev_cs = set(monthly_custs[monthly_custs["period"]==prev_p][self.customer_col])
                curr_cs = set(monthly_custs[monthly_custs["period"]==p][self.customer_col])
                curr_df = monthly_custs[monthly_custs["period"]==p]
                prev_df = monthly_custs[monthly_custs["period"]==prev_p]

                new_rev      = float(curr_df[curr_df[self.customer_col].isin(curr_cs - prev_cs)][self.metric_col].sum())
                retained_rev = float(curr_df[curr_df[self.customer_col].isin(curr_cs & prev_cs)][self.metric_col].sum())
                churned_rev  = float(prev_df[prev_df[self.customer_col].isin(prev_cs - curr_cs)][self.metric_col].sum())
                records.append({
                    "period":   str(p),
                    "new":      round(new_rev, 2),
                    "retained": round(retained_rev, 2),
                    "churned":  round(-churned_rev, 2),
                })

            self.result["growth"] = {
                "chart": self._chart_growth_accounting(records),
                "data":  records[-12:],
            }
        except Exception as e:
            self.logger.exception(f"Growth accounting analysis failed for date_col='{self.date_col}', customer_col='{self.customer_col}', metric_col='{self.metric_col}'")
            self.result["growth"] = {"error": str(e)}

    def _chart_growth_accounting(self, records):
        recs    = records[-12:]
        periods  = [r["period"]   for r in recs]
        new      = [r["new"]      for r in recs]
        retained = [r["retained"] for r in recs]
        churned  = [r["churned"]  for r in recs]
        x = range(len(periods))
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.bar(x, new,      label="New Revenue",      color=GREEN,  alpha=0.85)
        ax.bar(x, retained, label="Retained Revenue", color=ACCENT, alpha=0.85, bottom=new)
        ax.bar(x, churned,  label="Churned Revenue",  color=RED,    alpha=0.85)
        ax.axhline(0, color="#ffffff30", linewidth=0.8)
        ax.set_xticks(list(x))
        ax.set_xticklabels(periods, rotation=45, ha="right", fontsize=7)
        ax.legend(fontsize=9)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.set_title("Growth Accounting — New vs Retained vs Churned", fontsize=12, pad=10)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Contribution Margin ───────────────────────────────────────────────────

    def _build_contribution_margin(self):
        if not self.metric_col:
            self.result["contribution"] = {"error": "Contribution margin needs a metric column"}
            return
        try:
            df       = self.df
            cat_cols = [c for c in df.select_dtypes("object").columns if c != self.customer_col]
            if not cat_cols:
                self.result["contribution"] = {"error": "No categorical columns to group by"}
                return

            results = {}
            for col in cat_cols[:3]:
                grp = df.groupby(col)[self.metric_col].agg(["sum","mean","count"]).round(2)
                grp["pct_of_total"] = (grp["sum"] / grp["sum"].sum() * 100).round(1)
                results[col] = (grp.reset_index()
                                .rename(columns={"sum":"total","mean":"avg","count":"count"})
                                .head(15).to_dict("records"))

            primary = cat_cols[0]
            self.result["contribution"] = {
                "chart":       self._chart_contribution(df, primary),
                "breakdowns":  results,
                "primary_col": primary,
            }
        except Exception as e:
            self.logger.exception(f"Contribution margin analysis failed for metric_col='{self.metric_col}'")
            self.result["contribution"] = {"error": str(e)}

    def _chart_contribution(self, df, group_col):
        grp   = df.groupby(group_col)[self.metric_col].sum().sort_values(ascending=False).head(10)
        total = grp.sum()
        pcts  = (grp / total * 100).round(1)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
        colors = PALETTE[:len(grp)]

        bars = ax1.bar(range(len(grp)), grp.values, color=colors, alpha=0.85)
        _add_labels(ax1, bars, fmt="{:.0f}", fontsize=7)
        ax1.set_xticks(range(len(grp)))
        ax1.set_xticklabels(grp.index.astype(str), rotation=45, ha="right", fontsize=7)
        ax1.set_title(f"Total {self.metric_col} by {group_col}", fontsize=11, pad=10)
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))

        wedges, texts, autotexts = ax2.pie(
            pcts.values, labels=grp.index.astype(str),
            autopct="%1.1f%%", colors=colors,
            startangle=140, pctdistance=0.8,
            wedgeprops=dict(width=0.55),
        )
        for t in texts:     t.set_color("#e8e8f5"); t.set_fontsize(8)
        for t in autotexts: t.set_color("#0d0d1a"); t.set_fontweight("bold"); t.set_fontsize(7)
        ax2.set_title(f"% Contribution by {group_col}", fontsize=11, pad=10)
        fig.suptitle("Contribution Margin Analysis", fontsize=13)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Velocity Tracking ─────────────────────────────────────────────────────

    def _build_velocity(self):
        if not self.date_col or not self.metric_col:
            self.result["velocity"] = {"error": "Velocity tracking needs date and metric columns"}
            return
        try:
            ts = (self.df[[self.date_col, self.metric_col]]
                  .dropna().sort_values(self.date_col)
                  .set_index(self.date_col)[self.metric_col]
                  .resample(_RESAMPLE_MONTH).sum())

            velocity     = ts.diff()
            acceleration = velocity.diff()

            self.result["velocity"] = {
                "chart":   self._chart_velocity(ts, velocity, acceleration),
                "summary": (
                    f"Latest velocity: {float(velocity.iloc[-1]):+,.2f}. "
                    f"Acceleration: {float(acceleration.iloc[-1]):+,.2f}."
                ),
            }
        except Exception as e:
            self.logger.exception(f"Velocity tracking analysis failed for date_col='{self.date_col}', metric_col='{self.metric_col}'")
            self.result["velocity"] = {"error": str(e)}

    def _chart_velocity(self, ts, velocity, acceleration):
        fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
        axes[0].plot(ts.index, ts.values, color=ACCENT, linewidth=2)
        axes[0].fill_between(ts.index, ts.values, alpha=0.12, color=ACCENT)
        axes[0].set_title(f"{self.metric_col.replace('_',' ').title()} (Value)", fontsize=10)
        axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

        v_colors = [GREEN if v >= 0 else RED for v in velocity.fillna(0)]
        axes[1].bar(velocity.index, velocity.fillna(0), color=v_colors, alpha=0.8, width=25)
        axes[1].axhline(0, color="#ffffff30", linewidth=0.8)
        axes[1].set_title("Velocity (Month-over-Month Change)", fontsize=10)

        a_colors = [TEAL if a >= 0 else ORANGE for a in acceleration.fillna(0)]
        axes[2].bar(acceleration.index, acceleration.fillna(0), color=a_colors, alpha=0.8, width=25)
        axes[2].axhline(0, color="#ffffff30", linewidth=0.8)
        axes[2].set_title("Acceleration (Change in Velocity)", fontsize=10)

        fig.suptitle("Velocity Tracking", fontsize=13)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── Period Comparison ─────────────────────────────────────────────────────

    def _build_period_comparison(self):
        if not self.date_col or not self.metric_col:
            self.result["period"] = {"error": "Period comparison needs date and metric columns"}
            return
        try:
            ts = (self.df[[self.date_col, self.metric_col]]
                  .dropna().sort_values(self.date_col)
                  .set_index(self.date_col)[self.metric_col]
                  .resample(_RESAMPLE_QUARTER).sum())

            if len(ts) < 2:
                self.result["period"] = {"error": "Not enough periods to compare"}
                return

            last4 = ts.tail(4)
            prev4 = ts.iloc[-8:-4] if len(ts) >= 8 else ts.head(len(ts)//2)

            change_pct = ((last4.sum() - prev4.sum()) / max(abs(prev4.sum()), 1)) * 100
            self.result["period"] = {
                "chart":          self._chart_period_comparison(last4, prev4),
                "current_total":  round(float(last4.sum()), 2),
                "previous_total": round(float(prev4.sum()), 2),
                "change_pct":     round(float(change_pct), 2),
                "summary": (
                    f"Current period: {last4.sum():,.2f} vs "
                    f"Previous: {prev4.sum():,.2f} ({change_pct:+.1f}%)"
                ),
            }
        except Exception as e:
            self.logger.exception(f"Period comparison analysis failed for date_col='{self.date_col}', metric_col='{self.metric_col}'")
            self.result["period"] = {"error": str(e)}

    def _chart_period_comparison(self, current, previous):
        fig, ax = plt.subplots(figsize=(10, 5))
        x      = np.arange(len(current))
        width  = 0.35
        labels = [str(p)[:7] for p in current.index]

        bars1 = ax.bar(x - width/2, previous.values, width, color=ACCENT, alpha=0.65, label="Previous Period")
        bars2 = ax.bar(x + width/2, current.values,  width, color=GREEN,  alpha=0.85, label="Current Period")
        _add_labels(ax, bars1, fmt="{:.0f}", fontsize=7)
        _add_labels(ax, bars2, fmt="{:.0f}", fontsize=7)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        ax.legend(fontsize=9)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.set_title(f"Period Comparison — {self.metric_col.replace('_',' ').title()}", fontsize=12, pad=10)
        fig.tight_layout()
        return self._fig_to_b64(fig)

    # ── AI-Style Summary ──────────────────────────────────────────────────────

    def _build_ai_summary(self):
        summaries = {}
        kpi    = self.result.get("kpi", {})
        sc     = self.result.get("quality_scorecard", {})
        anom   = self.result.get("anomalies", {})
        s      = kpi.get("summary", {})
        domain = self.domain

        score    = sc.get("quality_score", 0)
        q_status = ("excellent" if score >= 85 else
                    "good"     if score >= 70 else
                    "moderate" if score >= 55 else "poor")
        trend_dir  = "growing" if (s.get("avg_mom_pct", 0) or 0) > 0 else "declining"
        mom        = s.get("avg_mom_pct", 0) or 0
        total      = s.get("total", 0) or 0
        months     = s.get("months", 0) or 0
        metric_lbl = (self.metric_col or "metric").replace("_", " ")
        crit_count = anom.get("critical", 0)

        summaries["overview"] = (
            f"This is a {domain} dataset with {q_status} data quality (score: {score}/100). "
            f"Across {months} months of data, total {metric_lbl} reached {total:,.2f} "
            f"with an average month-over-month change of {mom:+.1f}% — the business is currently {trend_dir}. "
            + (f"⚠ {crit_count} critical anomalies need immediate attention."
               if crit_count > 0 else "✓ No critical anomalies detected.")
        )

        if s:
            best  = s.get("best_month",  {})
            worst = s.get("worst_month", {})
            summaries["kpi"] = (
                f"Peak performance was in {best.get('period','—')} ({best.get('value',0):,.2f}), "
                f"while the weakest period was {worst.get('period','—')} ({worst.get('value',0):,.2f}). "
                f"Average monthly {metric_lbl}: {s.get('avg_monthly',0):,.2f}."
            )

        at = self.analysis_type
        if at == "rfm" and self.result.get("rfm"):
            rfm  = self.result["rfm"]
            segs = rfm.get("segments", [])
            champions = next((x for x in segs if x.get("Segment") == "Champions"), None)
            lost      = next((x for x in segs if x.get("Segment") == "Lost"), None)
            summaries["analysis"] = (
                f"RFM segmentation identified {rfm.get('total_customers',0):,} customers. "
                + (f"Champions ({int(champions.get('Count',0)):,} customers) average "
                   f"{champions.get('Avg_Mon',0):,.2f} in spend. " if champions else "")
                + (f"Lost customers ({int(lost.get('Count',0)):,}) haven't purchased recently "
                   f"and need reactivation campaigns." if lost else "")
            )
        elif at == "funnel" and self.result.get("funnel"):
            data = self.result["funnel"].get("data", [])
            if data:
                top    = data[0]
                bottom = data[-1]
                summaries["analysis"] = (
                    f"Funnel starts with {top.get('count',0):,} {top.get('stage','')} entries. "
                    f"Overall conversion rate to final stage: {bottom.get('conv_pct',0):.1f}%. "
                    f"Biggest drop-off point requires process optimisation."
                )
        elif at == "trend" and self.result.get("trend"):
            summaries["analysis"] = self.result["trend"].get("summary", "")
        elif at == "pareto" and self.result.get("pareto"):
            summaries["analysis"] = self.result["pareto"].get("summary", "")
        elif at == "price" and self.result.get("price"):
            summaries["analysis"] = self.result["price"].get("summary", "")
        elif at == "period" and self.result.get("period"):
            summaries["analysis"] = self.result["period"].get("summary", "")
        elif at == "velocity" and self.result.get("velocity"):
            summaries["analysis"] = self.result["velocity"].get("summary", "")

        if anom.get("total", 0) > 0:
            types    = Counter(a["type"] for a in anom.get("alerts", []))
            top_type = types.most_common(1)[0][0] if types else "Unknown"
            summaries["anomalies"] = (
                f"{anom['total']} anomalies detected: {anom.get('critical',0)} critical, "
                f"{anom.get('warnings',0)} warnings. "
                f"Most common issue: {top_type}. Review flagged columns before drawing conclusions."
            )
        else:
            summaries["anomalies"] = (
                "No anomalies detected. Data distribution looks healthy across all numeric columns."
            )

        self.result["ai_summaries"] = summaries

    # ── HTML Report ───────────────────────────────────────────────────────────

    # Consider breaking this long function into smaller, more focused helper methods for readability and maintainability.
    def _build_report_html(self):
        sc        = self.result.get("quality_scorecard", {})
        kpi       = self.result.get("kpi", {})
        anom      = self.result.get("anomalies", {})
        an_type   = self.analysis_type
        summaries = self.result.get("ai_summaries", {})

        # ── Pre-compute all conditional HTML blocks (avoids nested f-strings) ──
        kpi_charts_html = ""
        if kpi.get("charts"):
            for name, b64 in kpi["charts"].items():
                kpi_charts_html += (
                    f'<div class="chart-block">'
                    f'<img src="data:image/png;base64,{b64}"/></div>'
                )

        analysis_chart_html = ""
        for key in ["rfm","cohort","funnel","ops","seasonal","trend","pareto",
                    "price","growth","contribution","velocity","period"]:
            section = self.result.get(key, {})
            if isinstance(section, dict) and "charts" in section:
                for b64 in section["charts"].values():
                    analysis_chart_html += (
                        f'<div class="chart-block">'
                        f'<img src="data:image/png;base64,{b64}"/></div>'
                    )
            elif isinstance(section, dict) and section.get("chart"):
                analysis_chart_html += (
                    f'<div class="chart-block">'
                    f'<img src="data:image/png;base64,{section["chart"]}"/></div>'
                )

        alert_rows = ""
        for a in anom.get("alerts", [])[:20]:
            icon = "🔴" if a["severity"] == "CRITICAL" else "🟡"
            alert_rows += (
                f"<tr><td>{icon}</td><td>{a['type']}</td>"
                f"<td>{a['column']}</td><td>{a['description']}</td></tr>"
            )

        # Pre-compute summary boxes (avoids nested f-strings — Python < 3.12 safe)
        overview_html  = (f'<div class="summary-box">{summaries["overview"]}</div>'
                          if summaries.get("overview") else "")
        kpi_summ_html  = (f'<div class="summary-box">{summaries["kpi"]}</div>'
                          if summaries.get("kpi") else "")
        anal_summ_html = (f'<div class="summary-box">{summaries["analysis"]}</div>'
                          if summaries.get("analysis") else "")
        anom_summ_html = (f'<div class="summary-box">{summaries["anomalies"]}</div>'
                          if summaries.get("anomalies") else "")

        if anom.get("total", 0) == 0:
            alerts_section = '<p style="color:#3de8b0;padding:1rem 0;">✓ No anomalies detected.</p>'
        else:
            alerts_section = "".join([
                "<table>"
                "<thead><tr><th>Sev</th><th>Type</th><th>Column</th><th>Description</th></tr></thead>"
                f"<tbody>{alert_rows}</tbody>"
                "</table>"
            ])

        kpi_section      = kpi_charts_html      if kpi_charts_html      else '<p style="color:var(--muted)">No date/metric column detected.</p>'
        analysis_section = analysis_chart_html  if analysis_chart_html  else '<p style="color:var(--muted)">No analysis charts available.</p>'

        score        = sc.get("quality_score", 0)
        score_cls    = "g" if score >= 80 else ("y" if score >= 60 else "r")
        now          = datetime.now().strftime("%Y-%m-%d %H:%M")
        metric_label = (self.metric_col or "metric").replace("_", " ").title()
        kpi_summary  = kpi.get("summary", {})
        total_val    = kpi_summary.get("total", 0)
        avg_mom      = kpi_summary.get("avg_mom_pct", 0)
        mom_cls      = "g" if avg_mom >= 0 else "r"
        
        html_parts = [
            f'<!DOCTYPE html>\n'
            f'<html lang="en">\n'
            f'<head>\n'
            f'<meta charset="UTF-8"/>'
            f'<meta name="viewport" content="width=device-width,initial-scale=1.0"/>\n'
            f'<title>Insight Flow Report — {now}</title>\n'
            f'<style>\n'
            f':root{{--bg:#0a0a16;--surface:#11111e;--border:#1e1e35;--accent:#7c6fff;'
            f'--green:#3de8b0;--red:#ff5f7e;--yellow:#ffc947;--text:#e8e8f5;'
            f'--muted:#6b6b8a;--card:#13131f;}}\n'
            f'*{{box-sizing:border-box;margin:0;padding:0;}}\n'
            f'body{{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;'
            f'font-size:14px;line-height:1.6;}}\n'
            f'header{{background:var(--surface);border-bottom:1px solid var(--border);'
            f'padding:1.25rem 2rem;display:flex;justify-content:space-between;align-items:center;}}\n'
            f'.logo{{font-size:1.3rem;font-weight:800;}} .logo span{{color:var(--accent);}}\n'
            f'.by{{font-size:.8rem;color:var(--muted);margin-top:.15rem;}}\n'
            f'.meta{{font-size:0.78rem;color:var(--muted);text-align:right;}}\n'
            f'main{{max-width:1100px;margin:0 auto;padding:2rem;}}\n'
            f'h2{{font-size:1.05rem;font-weight:700;margin:2rem 0 0.75rem;'
            f'padding-bottom:0.5rem;border-bottom:1px solid var(--border);}}\n'
            f'h2:first-child{{margin-top:0;}}\n'
            f'.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));'
            f'gap:0.75rem;margin-bottom:1.5rem;}}\n'
            f'.card{{background:var(--card);border:1px solid var(--border);border-radius:8px;'
            f'padding:1rem;position:relative;overflow:hidden;}}\n'
            f'.card::before{{content:"";position:absolute;top:0;left:0;right:0;height:2px;'
            f'background:var(--accent);}}\n'
            f'.card.g::before{{background:var(--green);}}'
            f'.card.r::before{{background:var(--red);}}'
            f'.card.y::before{{background:var(--yellow);}}\n'
            f'.num{{font-size:1.6rem;font-weight:800;}} '
            f'.lbl{{font-size:0.72rem;color:var(--muted);margin-top:0.1rem;}}\n'
            f'.chart-block{{background:var(--card);border:1px solid var(--border);'
            f'border-radius:8px;overflow:hidden;margin-bottom:1rem;}}\n'
            f'.chart-block img{{width:100%;height:auto;display:block;}}\n'
            f'.summary-box{{background:rgba(124,111,255,.07);border:1px solid rgba(124,111,255,.2);'
            f'border-radius:8px;padding:1rem 1.25rem;margin-bottom:1.5rem;font-size:.88rem;'
            f'line-height:1.7;color:var(--text);}}\n'
            f'.domain-tag{{display:inline-block;padding:.2rem .6rem;border-radius:4px;'
            f'font-size:.72rem;font-weight:700;background:rgba(61,232,176,.12);'
            f'color:var(--green);margin-bottom:.5rem;}}\n'
            f'table{{width:100%;border-collapse:collapse;font-size:0.8rem;}}\n'
            f'th{{background:var(--surface);padding:0.5rem 0.75rem;text-align:left;'
            f'color:var(--muted);border-bottom:1px solid var(--border);}}\n'
            f'td{{padding:0.5rem 0.75rem;border-bottom:1px solid var(--border);}}\n'
            f'tr:last-child td{{border-bottom:none;}}\n'
            f'footer{{text-align:center;padding:1.5rem;color:var(--muted);'
            f'font-size:0.75rem;border-top:1px solid var(--border);margin-top:2rem;}}\n'
            f'</style>\n'
            f'</head>\n'
            f'<body>\n'
            f'<header>\n'
            f'  <div><div class="logo">Insight <span>Flow</span></div>'
            f'<div class="by">by Aadhya</div></div>\n'
            f'  <div class="meta">Generated {now}<br/>'
            f'Analysis: {an_type.upper()} · Domain: {self.domain}</div>\n'
            f'</header>\n'
            f'<main>\n\n'
            f'<h2>📊 Executive Summary</h2>\n'
            f'<div class="domain-tag">🏷 {self.domain} Domain</div>\n'
            f'{overview_html}\n'
            f'<div class="grid">\n'
            f'  <div class="card {score_cls}">\n'
            f'    <div class="num">{score}</div>\n'
            f'    <div class="lbl">Data Quality Score</div>\n'
            f'  </div>\n'
            f'  <div class="card">\n'
            f'    <div class="num">{sc.get("rows_after",0):,}</div>\n'
            f'    <div class="lbl">Clean Rows</div>\n'
            f'  </div>\n'
            f'  <div class="card">\n'
            f'    <div class="num">{sc.get("dupes_removed",0):,}</div>\n'
            f'    <div class="lbl">Dupes Removed</div>\n'
            f'  </div>\n'
            f'  <div class="card">\n'
            f'    <div class="num">{anom.get("total",0)}</div>\n'
            f'    <div class="lbl">Alerts Detected</div>\n'
            f'  </div>\n'
            f'  <div class="card g">\n'
            f'    <div class="num">{total_val:,.0f}</div>\n'
            f'    <div class="lbl">Total {metric_label}</div>\n'
            f'  </div>\n'
            f'  <div class="card {mom_cls}">\n'
            f'    <div class="num">{avg_mom:+.1f}%</div>\n'
            f'    <div class="lbl">Avg MoM Growth</div>\n'
            f'  </div>\n'
            f'</div>\n\n'
            f'<h2>📈 KPI Trends</h2>\n'
            f'{kpi_summ_html}\n'
            f'{kpi_section}\n\n'
            f'<h2>📊 {an_type.upper()} Analysis</h2>\n'
            f'{anal_summ_html}\n'
            f'{analysis_section}\n\n'
            f'<h2>🚨 Anomaly Alerts ({anom.get("total",0)})</h2>\n'
            f'{anom_summ_html}\n'
            f'{alerts_section}\n\n'
            f'</main>\n'
            f'<footer>Insight Flow · by Aadhya · {now}</footer>\n'
            f'</body>\n'
            f'</html>'
        ]
        html = "".join(html_parts)

        self.result["report_html"] = html

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fig_to_b64(self, fig) -> str:
        """
        Save figure to in-memory buffer, encode as base64, then ALWAYS close the
        figure to prevent matplotlib memory leaks — regardless of exceptions.
        """
        buf = io.BytesIO()
        try:
            fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                        facecolor=fig.get_facecolor())
            buf.seek(0)
            return base64.b64encode(buf.read()).decode()
        finally:
            plt.close(fig)   # FIX: guaranteed even if savefig raises

    def _df_to_json(self, df) -> list:
        d = df.copy()
        for c in d.select_dtypes("datetime64").columns:
            d[c] = d[c].astype(str)
        return d.fillna(0).round(3).to_dict("records")

    @staticmethod
    def get_available_analysis_types() -> List[str]:
        """Returns a list of all available analysis types that can be selected,
        including 'kpi' as a primary option."""
        # KPI is always run, but can also be the primary selected analysis type.
        return ["kpi"] + list(InsightFlowEngine._OPTIONAL_ANALYSIS_DISPATCH_MAP.keys())

# Backward-compatible alias
PulseBoardEngine = InsightFlowEngine



