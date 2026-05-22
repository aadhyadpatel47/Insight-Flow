"""
Insight Flow Engine — by Aadhya  v4.0
Fixes vs v3:
  - matplotlib.use("Agg") called once at module level, guarded
  - Every chart wrapped in try/except — one bad chart never kills the response
  - Lower DPI (85) + tight bbox for faster PNG encoding on serverless
  - Memory-safe: plt.close(fig) in finally block always
  - numpy polyfit replaces scipy (no extra dep)
  - RFM uses rank-based scoring (no duplicate-bin crash)
  - pandas resample shim for 2.2+ ("ME"/"QE")
  - Column name sync after clean()
  - No disk writes anywhere
"""
import os, tempfile

# Serverless filesystems usually only allow writes under /tmp. Matplotlib may
# create a font/config cache at import time, so point it somewhere writable
# before importing matplotlib.
os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "matplotlib"))

import matplotlib
matplotlib.use('Agg')
import io, base64, warnings, re, logging, traceback
import pandas as pd
import numpy as np
from datetime import datetime
from collections import Counter
from typing import List, Optional

warnings.filterwarnings("ignore")

# ── matplotlib — safe initialisation ─────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")          # must be before pyplot import
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import matplotlib.patches as mpatches
    _MPL_OK = True
except Exception:                  # pragma: no cover
    _MPL_OK = False

# ── pandas resample shim ──────────────────────────────────────────────────────
try:
    pd.Series(range(3), index=pd.date_range("2020-01", periods=3, freq="ME")).resample("ME").sum()
    _RM = "ME";  _RQ = "QE"
except Exception:
    _RM = "M";   _RQ = "Q"

# ── matplotlib global style ───────────────────────────────────────────────────
if _MPL_OK:
    plt.rcParams.update({
        "figure.facecolor":  "#0d0d1a",
        "axes.facecolor":    "#0d0d1a",
        "axes.edgecolor":    "#1e1e35",
        "axes.labelcolor":   "#9090b8",
        "xtick.color":       "#9090b8",
        "ytick.color":       "#9090b8",
        "text.color":        "#e8e8f5",
        "grid.color":        "#1e1e35",
        "grid.linewidth":    0.4,
        "font.family":       "DejaVu Sans",
        "axes.spines.top":   False,
        "axes.spines.right": False,
    })

A = "#7c6fff"; G = "#3de8b0"; R = "#ff5f7e"
Y = "#ffc947"; P = "#b06fff"; B = "#38c6f8"
O = "#ff8c42"; T = "#00d4aa"
PAL = [A, G, Y, R, P, B, O, T]

# ── helpers ───────────────────────────────────────────────────────────────────

def _clean_col_name(name: str) -> Optional[str]:
    if not name:
        return None
    name = name.strip().lower()
    name = re.sub(r"[\s\-/]+", "_", name)
    name = re.sub(r"[^\w]", "", name)
    return name or None


_DATE_TOKENS = {"date","time","dt","datetime","timestamp","created","updated",
                "period","day","week","month","year"}


def _looks_like_date_col(name: str) -> bool:
    c = _clean_col_name(str(name)) or ""
    if {t for t in c.split("_") if t} & _DATE_TOKENS:
        return True
    return c.endswith(("date","datetime","timestamp"))


def _parse_dt(series: pd.Series, col_name: str) -> Optional[pd.Series]:
    try:
        if pd.api.types.is_datetime64_any_dtype(series):
            return series
        if not _looks_like_date_col(col_name):
            return None
        non_null = series.dropna()
        if non_null.empty:
            return None
        cn = _clean_col_name(str(col_name)) or ""
        if pd.api.types.is_numeric_dtype(series):
            if cn != "year":
                return None
            yrs = pd.to_numeric(non_null, errors="coerce")
            if yrs.between(1900, 2100).mean() <= 0.8:
                return None
            parsed = pd.to_datetime(series.astype("Int64").astype(str), format="%Y", errors="coerce")
        else:
            sample = non_null.astype(str).str.strip()
            if sample.str.fullmatch(r"\d+(\.\d+)?").mean() > 0.9 and cn != "year":
                return None
            parsed = pd.to_datetime(series, errors="coerce")
        valid = parsed.notna()
        if valid.mean() <= 0.5:
            return None
        if parsed[valid].dt.year.between(1900, 2100).mean() <= 0.8:
            return None
        return parsed
    except Exception:
        return None


def _add_labels(ax, bars, fmt="{:.1f}", color="#e8e8f5", fs=8):
    for bar in bars:
        val = bar.get_height() if hasattr(bar, "get_height") else bar.get_width()
        try:
            lbl = fmt.format(float(val))
        except Exception:
            continue
        if abs(float(val)) < 1e-9:
            continue
        if hasattr(bar, "get_height"):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + abs(bar.get_height()) * 0.02,
                    lbl, ha="center", va="bottom", fontsize=fs, color=color, fontweight="600")
        else:
            ax.text(bar.get_width() + abs(bar.get_width()) * 0.01,
                    bar.get_y() + bar.get_height() / 2,
                    lbl, ha="left", va="center", fontsize=fs, color=color, fontweight="600")


# ── Engine ────────────────────────────────────────────────────────────────────

class InsightFlowEngine:

    MAX_ROWS = 50_000

    _DISPATCH = {
        "rfm":          "_build_rfm",
        "cohort":       "_build_cohort",
        "funnel":       "_build_funnel",
        "ops":          "_build_ops",
        "seasonal":     "_build_seasonal",
        "trend":        "_build_trend",
        "pareto":       "_build_pareto",
        "price":        "_build_price",
        "growth":       "_build_growth",
        "contribution": "_build_contribution",
        "velocity":     "_build_velocity",
        "period":       "_build_period",
    }

    def __init__(self, file_bytes: bytes, ext: str,
                 analysis_type: str = "kpi",
                 date_col=None, metric_col=None, customer_col=None):
        self.log = logging.getLogger(__name__)
        self.file_bytes    = file_bytes
        self.ext           = ext.lower()
        self.analysis_type = analysis_type.lower()
        self.date_col      = date_col
        self.metric_col    = metric_col
        self.customer_col  = customer_col
        self.df            = None
        self.sample        = None
        self.result        = {}
        self.audit         = []
        self.domain        = "General"

    # ── public ───────────────────────────────────────────────────────────────

    def run(self) -> dict:
        self._load()
        self._clean()
        self._auto_detect()
        self._detect_domain()
        self._make_sample()
        self._build_preview()
        self._build_quality()
        self._build_kpi()
        self._build_anomalies()

        if self.analysis_type in self._DISPATCH:
            fn = getattr(self, self._DISPATCH[self.analysis_type], None)
            if fn:
                try:
                    fn()
                except Exception as e:
                    self.log.error("Analysis %s failed: %s", self.analysis_type, e)
                    self.result[self.analysis_type] = {"error": str(e)}

        self._build_ai_summary()
        self._build_report_html()
        self.result.update({
            "audit":         self.audit,
            "analysis_type": self.analysis_type,
            "domain":        self.domain,
            "date_col":      self.date_col,
            "metric_col":    self.metric_col,
        })
        return self.result

    # ── load ─────────────────────────────────────────────────────────────────

    def _load(self):
        buf = io.BytesIO(self.file_bytes)
        if self.ext == ".csv":
            self.df = pd.read_csv(buf, low_memory=False)
        elif self.ext in (".xlsx", ".xls"):
            self.df = pd.read_excel(buf)
        elif self.ext == ".json":
            self.df = pd.read_json(buf)
        else:
            raise ValueError(f"Unsupported file type: {self.ext}")
        if not isinstance(self.df, pd.DataFrame):
            self.df = pd.DataFrame(self.df)
        if self.df.empty or len(self.df.columns) == 0:
            raise ValueError("The uploaded file does not contain any tabular data")

    # ── clean ─────────────────────────────────────────────────────────────────

    def _clean(self):
        df = self.df
        if df is None or df.empty:
            raise ValueError("The uploaded file does not contain any rows")
        br = len(df);  bn = int(df.isnull().sum().sum());  bd = int(df.duplicated().sum())

        df = df.drop_duplicates()
        for c in df.select_dtypes("object").columns:
            df[c] = df[c].str.strip()

        df.columns = (
            df.columns.str.strip().str.lower()
            .str.replace(r"[\s\-/]+", "_", regex=True)
            .str.replace(r"[^\w]", "", regex=True)
        )

        # sync user-specified cols
        for attr in ("date_col", "metric_col", "customer_col"):
            v = getattr(self, attr)
            if v:
                c = _clean_col_name(v)
                setattr(self, attr, c if c in df.columns else None)

        drop_cols = df.columns[df.isnull().mean() > 0.90].tolist()
        df = df.drop(columns=drop_cols)

        for c in df.select_dtypes("number").columns:
            if df[c].isnull().any():
                df[c] = df[c].fillna(df[c].median())
        for c in df.select_dtypes("object").columns:
            if df[c].isnull().any():
                df[c] = df[c].fillna("Unknown")

        for c in list(df.select_dtypes("object").columns):
            parsed = _parse_dt(df[c], c)
            if parsed is not None:
                df[c] = parsed

        for c in list(df.select_dtypes("object").columns):
            samp = df[c].dropna().head(50).astype(str)
            if samp.str.contains(r"[\$£₹,]", regex=True).any():
                cleaned = df[c].astype(str).str.replace(r"[\$£₹,\s]", "", regex=True)
                conv = pd.to_numeric(cleaned, errors="coerce")
                if conv.notna().sum() > len(df) * 0.5:
                    df[c] = conv

        for c in list(df.select_dtypes("number").columns):
            q1, q3 = df[c].quantile(0.25), df[c].quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                mask = (df[c] < q1 - 3*iqr) | (df[c] > q3 + 3*iqr)
                if mask.any():
                    df[f"{c}_outlier"] = mask.astype(int)

        key_cols = [c for c in df.columns if any(k in c.lower() for k in ["id","key","uid","ref"])]
        if key_cols:
            df = df.drop_duplicates(subset=key_cols, keep="first")
        if df.empty or len(df.columns) == 0:
            raise ValueError("No usable rows or columns remain after cleaning")

        self.df = df
        ar = len(df);  an = int(df.isnull().sum().sum())
        score = max(0, 100
                    - min((bn / max(br * max(len(df.columns), 1), 1)) * 40, 30)
                    - min((bd / max(br, 1)) * 30, 20))
        self.result["quality_scorecard"] = {
            "rows_before": br, "rows_after": ar, "cols": len(df.columns),
            "nulls_before": bn, "nulls_after": an, "dupes_removed": bd,
            "quality_score": round(score, 1), "dropped_cols": drop_cols,
        }
        self.audit.append(f"Cleaned: {br-ar} rows removed, {bn-an} nulls fixed")

    # ── domain ────────────────────────────────────────────────────────────────

    def _detect_domain(self):
        cols = " ".join(self.df.columns).lower()
        domains = {
            "Sales":      ["revenue","sales","order","deal","quota","invoice","discount","product","sku","unit_price"],
            "Marketing":  ["campaign","ctr","impression","click","conversion","lead","mql","channel","utm","spend","roas"],
            "Finance":    ["profit","margin","cost","expense","budget","forecast","cash","ebitda","balance","asset"],
            "HR":         ["employee","headcount","attrition","salary","tenure","hire","department","role","engagement"],
            "Operations": ["ticket","sla","handle_time","utilization","queue","backlog","throughput","incident"],
            "E-commerce": ["cart","checkout","basket","refund","return","sku","category","rating","review","shipping"],
        }
        scores = {d: sum(1 for k in kws if k in cols) for d, kws in domains.items()}
        best = max(scores, key=scores.get)
        self.domain = best if scores[best] >= 2 else "General"

    # ── auto-detect columns ───────────────────────────────────────────────────

    def _auto_detect(self):
        df = self.df
        if not self.date_col:
            for c in df.columns:
                p = _parse_dt(df[c], c)
                if p is not None:
                    df[c] = p; self.date_col = c; break

        if not self.metric_col:
            num = df.select_dtypes("number").columns.tolist()
            kws = ["revenue","sales","amount","value","price","spend","gmv","mrr","arr","total","profit","income"]
            for c in num:
                if any(k in c.lower() for k in kws):
                    self.metric_col = c; break
            if not self.metric_col:
                clean = [c for c in num if not c.endswith(("_outlier","_pct_rank"))]
                if clean:
                    self.metric_col = clean[0]

        if not self.customer_col:
            for c in df.columns:
                if any(k in c.lower() for k in ["customer","user","client","member","id"]):
                    self.customer_col = c; break

        self.result["detected"] = {
            "date_col": self.date_col, "metric_col": self.metric_col,
            "customer_col": self.customer_col,
            "total_rows": len(df), "total_cols": len(df.columns),
            "columns": list(df.columns),
        }

    def _make_sample(self):
        if len(self.df) > self.MAX_ROWS:
            self.sample = self.df.sample(self.MAX_ROWS, random_state=42)
            self.audit.append(f"Large file: sampled {self.MAX_ROWS:,} rows for charts")
        else:
            self.sample = self.df

    # ── preview ───────────────────────────────────────────────────────────────

    def _build_preview(self):
        prev = self.df.head(10).copy()
        for c in prev.select_dtypes("datetime64").columns:
            prev[c] = prev[c].astype(str)
        self.result["preview"] = {
            "columns": list(prev.columns),
            "rows": prev.fillna("").values.tolist(),
        }

    # ── quality stats ─────────────────────────────────────────────────────────

    def _build_quality(self):
        df = self.df
        stats = []
        for c in df.columns:
            if c.endswith("_outlier"):
                continue
            nc = int(df[c].isnull().sum())
            stats.append({
                "col": c, "dtype": str(df[c].dtype),
                "null_count": nc,
                "fill_rate": round((1 - nc / len(df)) * 100, 1),
                "unique": int(df[c].nunique()),
            })
        self.result["col_stats"] = stats

    # ── KPI ───────────────────────────────────────────────────────────────────

    def _build_kpi(self):
        if not self.date_col or not self.metric_col:
            self.result["kpi"] = {"error": "No date or metric column detected"}
            return
        try:
            df = self.df[[self.date_col, self.metric_col]].dropna().copy()
            df = df.sort_values(self.date_col).set_index(self.date_col)

            mo = df[self.metric_col].resample(_RM).sum().reset_index()
            mo.columns = ["period", "value"]
            mo["mom_pct"] = mo["value"].pct_change() * 100

            qo = df[self.metric_col].resample(_RQ).sum().reset_index()
            qo.columns = ["period", "value"]
            qo["qoq_pct"] = qo["value"].pct_change() * 100

            s = mo["value"]
            bm = mo.loc[s.idxmax()]; wm = mo.loc[s.idxmin()]
            self.result["kpi"] = {
                "summary": {
                    "total": round(float(s.sum()), 2),
                    "avg_monthly": round(float(s.mean()), 2),
                    "avg_mom_pct": round(float(mo["mom_pct"].mean()), 2),
                    "best_month":  {"period": str(bm["period"])[:7], "value": round(float(bm["value"]), 2)},
                    "worst_month": {"period": str(wm["period"])[:7], "value": round(float(wm["value"]), 2)},
                    "months": len(mo),
                },
                "monthly":   self._df_json(mo),
                "quarterly": self._df_json(qo),
                "charts": {
                    "trend":  self._safe_chart(self._chart_kpi_trend,  mo),
                    "growth": self._safe_chart(self._chart_growth_bars, mo),
                    "qoq":    self._safe_chart(self._chart_qoq,         qo),
                    "box":    self._safe_chart(self._chart_box,  df, self.metric_col),
                },
            }
        except Exception as e:
            self.log.error("KPI build failed: %s", e)
            self.result["kpi"] = {"error": str(e)}

    def _chart_kpi_trend(self, mo):
        fig, ax = plt.subplots(figsize=(10, 3.8))
        ax.plot(mo["period"], mo["value"], color=A, lw=2.5, zorder=3)
        ax.fill_between(mo["period"], mo["value"], alpha=0.12, color=A)
        ax.scatter(mo["period"], mo["value"], color=A, s=30, zorder=4)
        step = max(1, len(mo) // 8)
        for i, (p, v) in enumerate(zip(mo["period"], mo["value"])):
            if i % step == 0:
                ax.text(p, v * 1.02, f"{v:,.0f}", ha="center", va="bottom", fontsize=7, color="#e8e8f5", fontweight="600")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.set_title(f"Monthly {self.metric_col.replace('_',' ').title()}", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    def _chart_growth_bars(self, mo):
        fig, ax = plt.subplots(figsize=(10, 3.2))
        vals = mo["mom_pct"].fillna(0)
        cols = [G if v >= 0 else R for v in vals]
        bars = ax.bar(mo["period"], vals, color=cols, width=20, alpha=0.85)
        _add_labels(ax, bars, fmt="{:.1f}%", fs=7)
        ax.axhline(0, color="#ffffff30", lw=0.8)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))
        ax.set_title("Month-over-Month Growth (%)", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    def _chart_qoq(self, qo):
        fig, ax = plt.subplots(figsize=(8, 3.2))
        labels = [str(p)[:7] for p in qo["period"]]
        vals = qo["qoq_pct"].fillna(0)
        bars = ax.bar(range(len(labels)), vals, color=[G if v >= 0 else R for v in vals], alpha=0.85)
        _add_labels(ax, bars, fmt="{:.1f}%", fs=7)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.axhline(0, color="#ffffff30", lw=0.8)
        ax.set_title("Quarter-over-Quarter Growth (%)", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    def _chart_box(self, df_idx, mc):
        fig, ax = plt.subplots(figsize=(5, 3.8))
        data = df_idx[mc].dropna()
        ax.boxplot(data, vert=True, patch_artist=True,
                   boxprops=dict(facecolor=A+"44", color=A),
                   medianprops=dict(color=G, lw=2),
                   whiskerprops=dict(color="#9090b8"),
                   capprops=dict(color="#9090b8"),
                   flierprops=dict(marker="o", color=R, alpha=0.4, markersize=3))
        med = float(data.median())
        ax.text(1.15, med, f"Median: {med:,.1f}", va="center", fontsize=8, color=G)
        ax.set_title(f"{mc.replace('_',' ').title()} Distribution", fontsize=10, pad=8)
        ax.set_xticklabels([mc.replace("_"," ").title()])
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── anomalies ─────────────────────────────────────────────────────────────

    def _build_anomalies(self):
        df = self.sample
        alerts = []
        num_cols = [c for c in df.select_dtypes("number").columns if not c.endswith(("_outlier","_pct_rank"))]

        for col in num_cols[:15]:
            series = df[col].dropna()
            if len(series) < 10:
                continue
            mean, std = series.mean(), series.std()
            if std == 0:
                continue
            zs = np.abs((series - mean) / std)
            for idx in zs[zs > 2.5].index[:3]:
                val = float(df.at[idx, col])
                z = float(zs[idx])
                pct = ((val - mean) / mean * 100) if mean != 0 else 0
                alerts.append({
                    "severity": "CRITICAL" if z > 3.75 else "WARNING",
                    "column": col, "value": round(val, 3), "z_score": round(z, 2),
                    "description": (f"{col.replace('_',' ').title()} is {abs(pct):.1f}% "
                                    f"{'above' if val > mean else 'below'} average "
                                    f"(z={z:.2f}). Value: {val:,.2f}, Mean: {mean:,.2f}"),
                    "type": "Z-Score Anomaly",
                })

        if self.date_col and self.metric_col:
            try:
                ts = (self.df[[self.date_col, self.metric_col]].dropna()
                      .sort_values(self.date_col).set_index(self.date_col)[self.metric_col]
                      .resample(_RM).sum())
                pch = ts.pct_change()
                for idx in pch[pch < -0.20].index:
                    drop = float(pch[idx]) * 100
                    loc = ts.index.get_loc(idx)
                    prev = float(ts.iloc[loc-1]) if loc > 0 else 0
                    curr = float(ts[idx])
                    alerts.append({
                        "severity": "CRITICAL" if drop < -0.40 else "WARNING",
                        "column": self.metric_col, "value": round(curr, 2), "z_score": None,
                        "description": (f"{self.metric_col.replace('_',' ').title()} dropped "
                                        f"{abs(drop):.1f}% in {str(idx)[:7]} "
                                        f"({prev:,.2f} → {curr:,.2f})"),
                        "type": "Period Drop",
                    })
            except Exception as e:
                self.log.warning("Period-drop anomaly failed: %s", e)

        for col in self.df.columns:
            np_ = self.df[col].isnull().mean()
            if np_ > 0.20:
                alerts.append({
                    "severity": "WARNING", "column": col,
                    "value": round(np_ * 100, 1), "z_score": None,
                    "description": f"Column '{col}' has {np_*100:.1f}% missing values.",
                    "type": "High Null Rate",
                })

        alerts.sort(key=lambda a: 0 if a["severity"] == "CRITICAL" else 1)
        chart = self._safe_chart(self._chart_alerts, alerts) if alerts else None
        self.result["anomalies"] = {
            "total": len(alerts),
            "critical": sum(1 for a in alerts if a["severity"] == "CRITICAL"),
            "warnings": sum(1 for a in alerts if a["severity"] == "WARNING"),
            "alerts": alerts[:30], "chart": chart,
        }

    def _chart_alerts(self, alerts):
        types = Counter(a["type"] for a in alerts)
        if not types:
            return None
        fig, ax = plt.subplots(figsize=(7, 3))
        cm = {"Z-Score Anomaly": A, "Period Drop": R, "High Null Rate": Y}
        bars = ax.barh(list(types.keys()), list(types.values()),
                       color=[cm.get(k, B) for k in types.keys()], alpha=0.85)
        for bar in bars:
            v = bar.get_width()
            ax.text(v + 0.05, bar.get_y() + bar.get_height()/2,
                    str(int(v)), va="center", fontsize=9, color="#e8e8f5", fontweight="600")
        ax.set_title("Alert Summary by Type", fontsize=11, pad=8)
        ax.invert_yaxis()
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── RFM ───────────────────────────────────────────────────────────────────

    def _build_rfm(self):
        if not all([self.customer_col, self.date_col, self.metric_col]):
            self.result["rfm"] = {"error": "RFM needs customer, date, and metric columns"}; return
        df = self.df[[self.customer_col, self.date_col, self.metric_col]].dropna().copy()
        snap = df[self.date_col].max() + pd.Timedelta(days=1)
        rfm = df.groupby(self.customer_col).agg(
            Recency=(self.date_col, lambda x: (snap - x.max()).days),
            Frequency=(self.date_col, "count"),
            Monetary=(self.metric_col, "sum"),
        ).reset_index()

        def _rscore(s, asc=True):
            pct = s.rank(pct=True, method="average")
            lbls = [1,2,3,4,5] if asc else [5,4,3,2,1]
            return pd.cut(pct, bins=[0,.2,.4,.6,.8,1.0], labels=lbls, include_lowest=True).astype(float)

        rfm["R_score"] = _rscore(rfm["Recency"], asc=False)
        rfm["F_score"] = _rscore(rfm["Frequency"])
        rfm["M_score"] = _rscore(rfm["Monetary"])
        rfm["RFM_score"] = rfm["R_score"] + rfm["F_score"] + rfm["M_score"]
        rfm["Segment"] = rfm["RFM_score"].apply(
            lambda s: "Champions" if s >= 13 else "Loyal" if s >= 10 else "At Risk" if s >= 7 else "Needs Attention" if s >= 4 else "Lost"
        )
        seg = rfm.groupby("Segment").agg(
            Count=("RFM_score","count"), Avg_Rec=("Recency","mean"),
            Avg_Freq=("Frequency","mean"), Avg_Mon=("Monetary","mean"),
        ).round(1).reset_index()

        self.result["rfm"] = {
            "segments": seg.to_dict("records"),
            "total_customers": len(rfm),
            "charts": {
                "pie":     self._safe_chart(self._chart_rfm_donut, rfm),
                "scatter": self._safe_chart(self._chart_rfm_scatter, rfm),
                "bar":     self._safe_chart(self._chart_rfm_bar, seg),
            },
            "sample": rfm.head(100).fillna(0).round(2).to_dict("records"),
        }

    def _chart_rfm_donut(self, rfm):
        sc = rfm["Segment"].value_counts()
        fig, ax = plt.subplots(figsize=(5.5, 4.5))
        ws, ts, ats = ax.pie(sc.values, labels=sc.index, autopct="%1.1f%%",
                             colors=PAL[:len(sc)], startangle=140, pctdistance=0.75,
                             wedgeprops=dict(width=0.55))
        for t in ts:  t.set_color("#e8e8f5"); t.set_fontsize(9)
        for t in ats: t.set_color("#0d0d1a"); t.set_fontweight("bold"); t.set_fontsize(8)
        ax.set_title("Customer Segments (RFM)", fontsize=11, pad=8)
        ax.text(0, 0, f"{len(rfm):,}\nCustomers", ha="center", va="center", fontsize=9, color="#e8e8f5", fontweight="bold")
        fig.tight_layout()
        return self._fig_b64(fig)

    def _chart_rfm_scatter(self, rfm):
        fig, ax = plt.subplots(figsize=(7, 4))
        sc = ax.scatter(rfm["Recency"], rfm["Monetary"], c=rfm["RFM_score"],
                        cmap="plasma", alpha=0.5, s=12, vmin=3, vmax=15)
        plt.colorbar(sc, ax=ax, label="RFM Score")
        ax.set_xlabel("Recency (days)"); ax.set_ylabel("Monetary Value")
        ax.set_title("Recency vs Monetary", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    def _chart_rfm_bar(self, seg):
        fig, ax = plt.subplots(figsize=(6.5, 3.8))
        cm = {"Champions": G, "Loyal": A, "At Risk": Y, "Needs Attention": O, "Lost": R}
        bars = ax.barh(seg["Segment"], seg["Count"],
                       color=[cm.get(s, B) for s in seg["Segment"]], alpha=0.85)
        for bar in bars:
            v = bar.get_width()
            ax.text(v+0.4, bar.get_y()+bar.get_height()/2,
                    f"{int(v):,}", va="center", fontsize=9, color="#e8e8f5", fontweight="600")
        ax.set_title("Customers per Segment", fontsize=11, pad=8)
        ax.invert_yaxis(); fig.tight_layout()
        return self._fig_b64(fig)

    # ── cohort ────────────────────────────────────────────────────────────────

    def _build_cohort(self):
        df = self.sample
        dcols = df.select_dtypes("datetime64").columns.tolist()
        if not dcols:
            self.result["cohort"] = {"error": "Cohort needs a date column"}; return
        df = df.copy()
        df["cohort_month"] = df[dcols[0]].dt.to_period("M")
        if not self.metric_col:
            self.result["cohort"] = {"error": "No metric column"}; return
        aov = df.groupby("cohort_month")[self.metric_col].agg(AOV="mean", Total="sum", Count="count").round(2).reset_index()
        aov["cohort_month"] = aov["cohort_month"].astype(str)
        self.result["cohort"] = {
            "data": aov.to_dict("records"),
            "chart": self._safe_chart(self._chart_cohort_aov, aov),
        }

    def _chart_cohort_aov(self, aov):
        fig, ax = plt.subplots(figsize=(10, 3.8))
        bars = ax.bar(aov["cohort_month"], aov["AOV"], color=A, alpha=0.8)
        _add_labels(ax, bars, fmt="{:.0f}", fs=7)
        ax.plot(aov["cohort_month"], aov["AOV"], color=G, lw=1.5, marker="o", markersize=3, zorder=5)
        ax.set_title("Average Order Value per Cohort Month", fontsize=11, pad=8)
        plt.xticks(rotation=45, ha="right", fontsize=7)
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── funnel ────────────────────────────────────────────────────────────────

    def _build_funnel(self):
        df = self.df
        sc = None
        for c in df.select_dtypes("object").columns:
            if any(k in c.lower() for k in ["stage","step","status","phase","funnel"]):
                sc = c; break
        if not sc:
            for c in df.select_dtypes("object").columns:
                if 2 <= df[c].nunique() <= 12:
                    sc = c; break
        if not sc:
            self.result["funnel"] = {"error": "No stage/status column found"}; return
        counts = df[sc].value_counts().reset_index()
        counts.columns = ["stage","count"]
        counts["conv_pct"] = (counts["count"] / counts["count"].iloc[0] * 100).round(1)
        self.result["funnel"] = {
            "data": counts.to_dict("records"),
            "chart": self._safe_chart(self._chart_funnel, counts),
            "stage_col": sc,
        }

    def _chart_funnel(self, counts):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        bars = ax.barh(counts["stage"], counts["count"], color=PAL[:len(counts)], alpha=0.85)
        for bar, pct in zip(bars, counts["conv_pct"]):
            w = bar.get_width()
            ax.text(w + counts["count"].max() * 0.01, bar.get_y() + bar.get_height()/2,
                    f"{pct:.1f}%  ({int(w):,})", va="center", fontsize=9, color="#e8e8f5", fontweight="600")
        ax.invert_yaxis()
        ax.set_title("Funnel Conversion Analysis", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── ops ───────────────────────────────────────────────────────────────────

    def _build_ops(self):
        if not self.date_col or not self.metric_col:
            self.result["ops"] = {"error": "Ops needs date and metric columns"}; return
        df = (self.sample[[self.date_col, self.metric_col]].dropna()
              .sort_values(self.date_col).set_index(self.date_col)[self.metric_col])
        ma7 = df.rolling(7).mean(); ma30 = df.rolling(30).mean()
        std7 = df.rolling(7).std()
        upper = ma7 + 2*std7; lower = ma7 - 2*std7
        self.result["ops"] = {
            "chart": self._safe_chart(self._chart_ops, df, ma7, ma30, upper, lower),
            "summary": {
                "mean": round(float(df.mean()),2), "std": round(float(df.std()),2),
                "max":  round(float(df.max()),2),  "min": round(float(df.min()),2),
            },
        }

    def _chart_ops(self, series, ma7, ma30, upper, lower):
        fig, ax = plt.subplots(figsize=(11, 4.5))
        ax.plot(series.index, series, color="#94A3B8", lw=0.7, alpha=0.5, label="Actual")
        ax.plot(series.index, ma7,   color=A, lw=1.8, label="7-day MA")
        ax.plot(series.index, ma30,  color=G, lw=1.8, label="30-day MA")
        ax.fill_between(series.index, lower, upper, alpha=0.07, color=A, label="Bollinger ±2σ")
        ax.legend(fontsize=8)
        ax.set_title(f"Ops Trend — {self.metric_col}", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── seasonal ──────────────────────────────────────────────────────────────

    def _build_seasonal(self):
        if not self.date_col or not self.metric_col:
            self.result["seasonal"] = {"error": "Seasonal needs date and metric columns"}; return
        df = self.sample[[self.date_col, self.metric_col]].dropna().copy()
        df["month"] = df[self.date_col].dt.month
        df["quarter"] = df[self.date_col].dt.quarter
        df["year"] = df[self.date_col].dt.year
        df["dow"] = df[self.date_col].dt.dayofweek
        mav = df.groupby("month")[self.metric_col].mean()
        qv  = df.groupby("quarter")[self.metric_col].sum()
        yv  = df.groupby("year")[self.metric_col].sum()
        dov = df.groupby("dow")[self.metric_col].mean()
        self.result["seasonal"] = {
            "chart": self._safe_chart(self._chart_seasonal, mav, qv, yv, dov),
            "monthly_avg": {str(k): round(float(v),2) for k,v in mav.items()},
            "quarterly_sum": {str(k): round(float(v),2) for k,v in qv.items()},
        }

    def _chart_seasonal(self, mav, qv, yv, dov):
        mn = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        dn = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        fig, axes = plt.subplots(2, 2, figsize=(12, 7))
        fig.suptitle(f"Seasonal Patterns — {self.metric_col}", fontsize=12)
        v0 = mav.reindex(range(1,13)).fillna(0)
        b0 = axes[0,0].bar(range(1,13), v0, color=A, alpha=0.85)
        _add_labels(axes[0,0], b0, fmt="{:.0f}", fs=6)
        axes[0,0].set_xticks(range(1,13)); axes[0,0].set_xticklabels(mn, rotation=45, fontsize=7)
        axes[0,0].set_title("Avg by Month")
        v1 = qv.reindex([1,2,3,4]).fillna(0)
        b1 = axes[0,1].bar([1,2,3,4], v1, color=P, alpha=0.85)
        _add_labels(axes[0,1], b1, fmt="{:.0f}", fs=7)
        axes[0,1].set_xticks([1,2,3,4]); axes[0,1].set_xticklabels(["Q1","Q2","Q3","Q4"])
        axes[0,1].set_title("Total by Quarter")
        axes[1,0].plot(yv.index, yv.values, marker="o", color=G, lw=2)
        for x2, y2 in zip(yv.index, yv.values):
            axes[1,0].text(x2, y2*1.02, f"{y2:,.0f}", ha="center", va="bottom", fontsize=7, color=G)
        axes[1,0].set_title("Total by Year")
        v3 = dov.reindex(range(7)).fillna(0)
        b3 = axes[1,1].bar(range(7), v3, color=Y, alpha=0.85)
        _add_labels(axes[1,1], b3, fmt="{:.0f}", fs=7)
        axes[1,1].set_xticks(range(7)); axes[1,1].set_xticklabels(dn)
        axes[1,1].set_title("Avg by Day of Week")
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── trend ─────────────────────────────────────────────────────────────────

    def _build_trend(self):
        if not self.date_col or not self.metric_col:
            self.result["trend"] = {"error": "Trend needs date and metric columns"}; return
        df = (self.df[[self.date_col, self.metric_col]].dropna()
              .sort_values(self.date_col).set_index(self.date_col))
        ts = df[self.metric_col].resample(_RM).sum()
        x = np.arange(len(ts)); y = ts.values.astype(float)
        coef = np.polyfit(x, y, 1)
        slope = float(coef[0]); tl = slope * x + float(coef[1])
        r = float(np.corrcoef(x, y)[0,1]) if y.std() > 0 else 0.0
        ma3 = ts.rolling(3).mean(); ma6 = ts.rolling(6).mean()
        direction = "upward" if slope > 0 else "downward"
        strength = "strong" if abs(r) > 0.7 else "moderate" if abs(r) > 0.4 else "weak"
        self.result["trend"] = {
            "chart": self._safe_chart(self._chart_trend, ts, tl, ma3, ma6),
            "slope": round(slope, 3), "r_squared": round(r**2, 3),
            "direction": direction, "strength": strength,
            "summary": f"The metric shows a {strength} {direction} trend (R²={r**2:.2f}). Avg monthly change: {slope:+,.2f}.",
        }

    def _chart_trend(self, ts, tl, ma3, ma6):
        fig, ax = plt.subplots(figsize=(11, 4.5))
        ax.bar(ts.index, ts.values, color=A, alpha=0.3, width=25, label="Monthly")
        ax.plot(ts.index, tl,  color=R, lw=2.2, ls="--", label="Linear Trend")
        ax.plot(ts.index, ma3, color=G, lw=1.8, label="3-Month MA")
        ax.plot(ts.index, ma6, color=Y, lw=1.8, label="6-Month MA")
        ax.legend(fontsize=8)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.set_title(f"Trend — {self.metric_col.replace('_',' ').title()}", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── pareto ────────────────────────────────────────────────────────────────

    def _build_pareto(self):
        if not self.metric_col:
            self.result["pareto"] = {"error": "Pareto needs a metric column"}; return
        df = self.df
        cat = [c for c in df.select_dtypes("object").columns if c not in [self.date_col, self.customer_col]]
        gc = cat[0] if cat else None
        if not gc:
            self.result["pareto"] = {"error": "No categorical column found"}; return
        grp = df.groupby(gc)[self.metric_col].sum().sort_values(ascending=False).reset_index()
        grp.columns = ["category","value"]
        grp["cumulative_pct"] = (grp["value"].cumsum() / grp["value"].sum() * 100).round(1)
        grp["pct_of_total"] = (grp["value"] / grp["value"].sum() * 100).round(1)
        ti = int((grp["cumulative_pct"] <= 80).sum())
        self.result["pareto"] = {
            "chart": self._safe_chart(self._chart_pareto, grp, ti),
            "group_col": gc, "top_items": ti,
            "data": grp.head(20).to_dict("records"),
            "summary": f"Top {ti} {gc} items drive 80% of total {self.metric_col}.",
        }

    def _chart_pareto(self, data, ti):
        top = data.head(20)
        fig, ax1 = plt.subplots(figsize=(11, 4.5))
        ax2 = ax1.twinx()
        colors = [G if i < ti else A for i in range(len(top))]
        ax1.bar(range(len(top)), top["value"], color=colors, alpha=0.8)
        ax2.plot(range(len(top)), top["cumulative_pct"], color=R, lw=2.2, marker="o", markersize=3)
        ax2.axhline(80, color=Y, lw=1.5, ls="--", alpha=0.7)
        ax2.set_ylabel("Cumulative %", color=R); ax2.set_ylim(0, 115)
        ax1.set_xticks(range(len(top)))
        ax1.set_xticklabels(top["category"].astype(str), rotation=45, ha="right", fontsize=7)
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax1.set_title(f"Pareto — {self.metric_col.replace('_',' ').title()}", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── price sensitivity ─────────────────────────────────────────────────────

    def _build_price(self):
        df = self.df
        num = df.select_dtypes("number").columns.tolist()
        pc = next((c for c in num if any(k in c.lower() for k in ["price","cost","rate","fee","charge"])), None)
        vc = next((c for c in num if any(k in c.lower() for k in ["quantity","volume","units","qty","count","orders"]) and c != pc), None)
        if not pc or not vc:
            self.result["price"] = {"error": "Need price/cost and volume/quantity columns"}; return
        data = df[[pc, vc]].dropna()
        data = data[data[pc] > 0].copy()
        data["price_bin"] = pd.qcut(data[pc], q=10, duplicates="drop")
        grp = data.groupby("price_bin", observed=True).agg(avg_price=(pc,"mean"), avg_volume=(vc,"mean"), count=(vc,"count")).reset_index()
        p_arr = data[pc].values.astype(float); v_arr = data[vc].values.astype(float)
        corr = float(np.corrcoef(p_arr, v_arr)[0,1]) if p_arr.std() > 0 and v_arr.std() > 0 else 0.0
        self.result["price"] = {
            "chart": self._safe_chart(self._chart_price, grp, pc, vc, corr),
            "price_col": pc, "volume_col": vc, "correlation": round(corr, 3),
            "summary": (f"Price-volume correlation: {corr:.2f}. " +
                        ("Higher price reduces demand (elastic)." if corr < -0.3 else
                         "Weak price-volume relationship." if abs(corr) < 0.3 else
                         "Higher price correlates with more volume (premium effect).")),
        }

    def _chart_price(self, grp, pc, vc, corr):
        fig, ax1 = plt.subplots(figsize=(9, 4.5))
        ax2 = ax1.twinx()
        ax1.bar(range(len(grp)), grp["avg_volume"], color=A, alpha=0.7, label="Avg Volume")
        ax2.plot(range(len(grp)), grp["avg_price"], color=R, lw=2.2, marker="o", markersize=4)
        ax1.set_ylabel("Avg Volume", color=A); ax2.set_ylabel("Avg Price", color=R)
        ax1.set_xticks(range(len(grp))); ax1.set_xticklabels([f"P{i+1}" for i in range(len(grp))], fontsize=8)
        ax1.set_title(f"Price Sensitivity — {pc} vs {vc} (corr={corr:.2f})", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── growth accounting ─────────────────────────────────────────────────────

    def _build_growth(self):
        if not all([self.date_col, self.customer_col, self.metric_col]):
            self.result["growth"] = {"error": "Growth accounting needs date, customer, and metric columns"}; return
        df = self.df[[self.date_col, self.customer_col, self.metric_col]].dropna().copy()
        df["period"] = df[self.date_col].dt.to_period("M")
        mc = df.groupby(["period", self.customer_col])[self.metric_col].sum().reset_index()
        periods = sorted(mc["period"].unique())
        records = []
        for i, p in enumerate(periods[1:], 1):
            pp = periods[i-1]
            pcs = set(mc[mc["period"]==pp][self.customer_col])
            ccs = set(mc[mc["period"]==p][self.customer_col])
            cdf = mc[mc["period"]==p]; pdf = mc[mc["period"]==pp]
            nr = float(cdf[cdf[self.customer_col].isin(ccs-pcs)][self.metric_col].sum())
            rr = float(cdf[cdf[self.customer_col].isin(ccs&pcs)][self.metric_col].sum())
            cr = float(pdf[pdf[self.customer_col].isin(pcs-ccs)][self.metric_col].sum())
            records.append({"period": str(p), "new": round(nr,2), "retained": round(rr,2), "churned": round(-cr,2)})
        self.result["growth"] = {
            "chart": self._safe_chart(self._chart_growth, records),
            "data": records[-12:],
        }

    def _chart_growth(self, records):
        recs = records[-12:]
        periods = [r["period"] for r in recs]
        new = [r["new"] for r in recs]; ret = [r["retained"] for r in recs]; chu = [r["churned"] for r in recs]
        x = range(len(periods))
        fig, ax = plt.subplots(figsize=(11, 4.5))
        ax.bar(x, new, label="New", color=G, alpha=0.85)
        ax.bar(x, ret, label="Retained", color=A, alpha=0.85, bottom=new)
        ax.bar(x, chu, label="Churned", color=R, alpha=0.85)
        ax.axhline(0, color="#ffffff30", lw=0.8)
        ax.set_xticks(list(x)); ax.set_xticklabels(periods, rotation=45, ha="right", fontsize=7)
        ax.legend(fontsize=8)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v,_: f"{v:,.0f}"))
        ax.set_title("Growth Accounting — New vs Retained vs Churned", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── contribution margin ───────────────────────────────────────────────────

    def _build_contribution(self):
        if not self.metric_col:
            self.result["contribution"] = {"error": "Contribution margin needs a metric column"}; return
        df = self.df
        cat = [c for c in df.select_dtypes("object").columns if c != self.customer_col]
        if not cat:
            self.result["contribution"] = {"error": "No categorical columns"}; return
        results = {}
        for col in cat[:3]:
            grp = df.groupby(col)[self.metric_col].agg(["sum","mean","count"]).round(2)
            grp["pct_of_total"] = (grp["sum"] / grp["sum"].sum() * 100).round(1)
            results[col] = grp.reset_index().rename(columns={"sum":"total","mean":"avg","count":"count"}).head(15).to_dict("records")
        self.result["contribution"] = {
            "chart": self._safe_chart(self._chart_contribution, df, cat[0]),
            "breakdowns": results, "primary_col": cat[0],
        }

    def _chart_contribution(self, df, gc):
        grp = df.groupby(gc)[self.metric_col].sum().sort_values(ascending=False).head(10)
        pcts = (grp / grp.sum() * 100).round(1)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
        colors = PAL[:len(grp)]
        bars = ax1.bar(range(len(grp)), grp.values, color=colors, alpha=0.85)
        _add_labels(ax1, bars, fmt="{:.0f}", fs=7)
        ax1.set_xticks(range(len(grp))); ax1.set_xticklabels(grp.index.astype(str), rotation=45, ha="right", fontsize=7)
        ax1.set_title(f"Total {self.metric_col} by {gc}", fontsize=10, pad=8)
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v,_: f"{v:,.0f}"))
        ws, ts, ats = ax2.pie(pcts.values, labels=grp.index.astype(str), autopct="%1.1f%%",
                              colors=colors, startangle=140, pctdistance=0.8, wedgeprops=dict(width=0.55))
        for t in ts:  t.set_color("#e8e8f5"); t.set_fontsize(8)
        for t in ats: t.set_color("#0d0d1a"); t.set_fontweight("bold"); t.set_fontsize(7)
        ax2.set_title(f"% Contribution by {gc}", fontsize=10, pad=8)
        fig.suptitle("Contribution Margin Analysis", fontsize=12)
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── velocity ──────────────────────────────────────────────────────────────

    def _build_velocity(self):
        if not self.date_col or not self.metric_col:
            self.result["velocity"] = {"error": "Velocity needs date and metric columns"}; return
        ts = (self.df[[self.date_col, self.metric_col]].dropna()
              .sort_values(self.date_col).set_index(self.date_col)[self.metric_col]
              .resample(_RM).sum())
        vel = ts.diff(); acc = vel.diff()
        self.result["velocity"] = {
            "chart": self._safe_chart(self._chart_velocity, ts, vel, acc),
            "summary": f"Latest velocity: {float(vel.iloc[-1]):+,.2f}. Acceleration: {float(acc.iloc[-1]):+,.2f}.",
        }

    def _chart_velocity(self, ts, vel, acc):
        fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
        axes[0].plot(ts.index, ts.values, color=A, lw=2)
        axes[0].fill_between(ts.index, ts.values, alpha=0.1, color=A)
        axes[0].set_title(f"{self.metric_col.replace('_',' ').title()} (Value)", fontsize=10)
        axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"{x:,.0f}"))
        vc = [G if v >= 0 else R for v in vel.fillna(0)]
        axes[1].bar(vel.index, vel.fillna(0), color=vc, alpha=0.8, width=25)
        axes[1].axhline(0, color="#ffffff30", lw=0.8); axes[1].set_title("Velocity (MoM Change)", fontsize=10)
        ac = [T if a >= 0 else O for a in acc.fillna(0)]
        axes[2].bar(acc.index, acc.fillna(0), color=ac, alpha=0.8, width=25)
        axes[2].axhline(0, color="#ffffff30", lw=0.8); axes[2].set_title("Acceleration", fontsize=10)
        fig.suptitle("Velocity Tracking", fontsize=12); fig.tight_layout()
        return self._fig_b64(fig)

    # ── period comparison ─────────────────────────────────────────────────────

    def _build_period(self):
        if not self.date_col or not self.metric_col:
            self.result["period"] = {"error": "Period comparison needs date and metric columns"}; return
        ts = (self.df[[self.date_col, self.metric_col]].dropna()
              .sort_values(self.date_col).set_index(self.date_col)[self.metric_col]
              .resample(_RQ).sum())
        if len(ts) < 2:
            self.result["period"] = {"error": "Not enough periods to compare"}; return
        last4 = ts.tail(4); prev4 = ts.iloc[-8:-4] if len(ts) >= 8 else ts.head(len(ts)//2)
        chg = ((last4.sum() - prev4.sum()) / max(abs(prev4.sum()), 1)) * 100
        self.result["period"] = {
            "chart": self._safe_chart(self._chart_period, last4, prev4),
            "current_total": round(float(last4.sum()),2),
            "previous_total": round(float(prev4.sum()),2),
            "change_pct": round(float(chg),2),
            "summary": f"Current: {last4.sum():,.2f} vs Previous: {prev4.sum():,.2f} ({chg:+.1f}%)",
        }

    def _chart_period(self, curr, prev):
        fig, ax = plt.subplots(figsize=(9, 4.5))
        n = max(len(curr), len(prev)); x = np.arange(n); w = 0.35
        labels = [str(p)[:7] for p in curr.index]
        if len(labels) < n: labels += [f"P{i+1}" for i in range(len(labels), n)]
        b1 = ax.bar(np.arange(len(prev))-w/2, prev.values, w, color=A, alpha=0.65, label="Previous")
        b2 = ax.bar(np.arange(len(curr))+w/2, curr.values, w, color=G, alpha=0.85, label="Current")
        _add_labels(ax, b1, fmt="{:.0f}", fs=7); _add_labels(ax, b2, fmt="{:.0f}", fs=7)
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
        ax.legend(fontsize=8)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v,_: f"{v:,.0f}"))
        ax.set_title(f"Period Comparison — {self.metric_col.replace('_',' ').title()}", fontsize=11, pad=8)
        fig.tight_layout()
        return self._fig_b64(fig)

    # ── AI summary ────────────────────────────────────────────────────────────

    def _build_ai_summary(self):
        sums = {}
        sc = self.result.get("quality_scorecard", {})
        kpi = self.result.get("kpi", {})
        anom = self.result.get("anomalies", {})
        s = kpi.get("summary", {})
        score = sc.get("quality_score", 0)
        qs = "excellent" if score>=85 else "good" if score>=70 else "moderate" if score>=55 else "poor"
        mom = s.get("avg_mom_pct", 0) or 0
        total = s.get("total", 0) or 0
        months = s.get("months", 0) or 0
        ml = (self.metric_col or "metric").replace("_"," ")
        crit = anom.get("critical", 0)
        sums["overview"] = (
            f"This is a {self.domain} dataset with {qs} data quality (score: {score}/100). "
            f"Across {months} months of data, total {ml} reached {total:,.2f} "
            f"with an average MoM change of {mom:+.1f}% — the business is {'growing' if mom>0 else 'declining'}. "
            + (f"⚠ {crit} critical anomalies need attention." if crit>0 else "✓ No critical anomalies detected.")
        )
        if s:
            bm = s.get("best_month", {}); wm = s.get("worst_month", {})
            sums["kpi"] = (f"Peak was {bm.get('period','—')} ({bm.get('value',0):,.2f}), "
                           f"weakest was {wm.get('period','—')} ({wm.get('value',0):,.2f}). "
                           f"Avg monthly {ml}: {s.get('avg_monthly',0):,.2f}.")
        at = self.analysis_type
        if at == "rfm" and self.result.get("rfm") and not self.result["rfm"].get("error"):
            rfm = self.result["rfm"]; segs = rfm.get("segments",[])
            ch = next((x for x in segs if x.get("Segment")=="Champions"), None)
            lo = next((x for x in segs if x.get("Segment")=="Lost"), None)
            sums["analysis"] = (f"RFM identified {rfm.get('total_customers',0):,} customers. "
                                 + (f"Champions ({int(ch.get('Count',0)):,}) avg {ch.get('Avg_Mon',0):,.2f} spend. " if ch else "")
                                 + (f"Lost customers ({int(lo.get('Count',0)):,}) need reactivation." if lo else ""))
        elif at in ("trend","pareto","price","period","velocity") and self.result.get(at) and not self.result[at].get("error"):
            sums["analysis"] = self.result[at].get("summary","")
        elif at == "funnel" and self.result.get("funnel") and not self.result["funnel"].get("error"):
            data = self.result["funnel"].get("data",[])
            if data:
                sums["analysis"] = (f"Funnel starts with {data[0].get('count',0):,} entries. "
                                     f"Overall conversion: {data[-1].get('conv_pct',0):.1f}%.")
        if anom.get("total",0) > 0:
            types = Counter(a["type"] for a in anom.get("alerts",[]))
            top_t = types.most_common(1)[0][0] if types else "Unknown"
            sums["anomalies"] = (f"{anom['total']} anomalies: {crit} critical, {anom.get('warnings',0)} warnings. "
                                  f"Most common: {top_t}.")
        else:
            sums["anomalies"] = "No anomalies detected. Data distribution looks healthy."
        self.result["ai_summaries"] = sums

    # ── HTML report ───────────────────────────────────────────────────────────

    def _build_report_html(self):
        sc = self.result.get("quality_scorecard",{})
        kpi = self.result.get("kpi",{})
        anom = self.result.get("anomalies",{})
        sums = self.result.get("ai_summaries",{})
        at = self.analysis_type
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        score = sc.get("quality_score",0)
        sc_cls = "g" if score>=80 else "y" if score>=60 else "r"
        ml = (self.metric_col or "metric").replace("_"," ").title()
        ks = kpi.get("summary",{})
        tv = ks.get("total",0); am = ks.get("avg_mom_pct",0)
        mom_cls = "g" if am>=0 else "r"

        # chart blocks
        kpi_charts = ""
        if kpi.get("charts"):
            for b64 in kpi["charts"].values():
                if b64:
                    kpi_charts += f'<div class="cb"><img src="data:image/png;base64,{b64}"/></div>'

        an_charts = ""
        for key in ["rfm","cohort","funnel","ops","seasonal","trend","pareto","price","growth","contribution","velocity","period"]:
            sec = self.result.get(key,{})
            if isinstance(sec, dict):
                if "charts" in sec:
                    for b64 in sec["charts"].values():
                        if b64:
                            an_charts += f'<div class="cb"><img src="data:image/png;base64,{b64}"/></div>'
                elif sec.get("chart"):
                    an_charts += f'<div class="cb"><img src="data:image/png;base64,{sec["chart"]}"/></div>'

        alert_rows = ""
        for a in anom.get("alerts",[])[:20]:
            ic = "🔴" if a["severity"]=="CRITICAL" else "🟡"
            alert_rows += f"<tr><td>{ic}</td><td>{a['type']}</td><td>{a['column']}</td><td>{a['description']}</td></tr>"

        alerts_html = ('<p style="color:#3de8b0;padding:.75rem 0">✓ No anomalies detected.</p>'
                       if not anom.get("total") else
                       f'<table><thead><tr><th>Sev</th><th>Type</th><th>Column</th><th>Description</th></tr></thead><tbody>{alert_rows}</tbody></table>')

        ov = f'<div class="sb">{sums.get("overview","")}</div>' if sums.get("overview") else ""
        ks2 = f'<div class="sb">{sums.get("kpi","")}</div>' if sums.get("kpi") else ""
        as2 = f'<div class="sb">{sums.get("analysis","")}</div>' if sums.get("analysis") else ""
        ano = f'<div class="sb">{sums.get("anomalies","")}</div>' if sums.get("anomalies") else ""

        html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Insight Flow Report — {now}</title>
<style>
:root{{--bg:#0a0a16;--sf:#11111e;--bd:#1e1e35;--ac:#7c6fff;--gn:#3de8b0;--rd:#ff5f7e;--yw:#ffc947;--tx:#e8e8f5;--mu:#6b6b8a;--cd:#13131f}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx);font-family:system-ui,sans-serif;font-size:14px;line-height:1.6}}
header{{background:var(--sf);border-bottom:1px solid var(--bd);padding:1.25rem 2rem;display:flex;justify-content:space-between;align-items:center}}
.logo{{font-size:1.3rem;font-weight:800}}.logo span{{color:var(--ac)}}
.by{{font-size:.8rem;color:var(--mu);margin-top:.15rem}}
.meta{{font-size:.78rem;color:var(--mu);text-align:right}}
main{{max-width:1100px;margin:0 auto;padding:2rem}}
h2{{font-size:1.05rem;font-weight:700;margin:2rem 0 .75rem;padding-bottom:.5rem;border-bottom:1px solid var(--bd)}}
h2:first-child{{margin-top:0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.75rem;margin-bottom:1.5rem}}
.card{{background:var(--cd);border:1px solid var(--bd);border-radius:8px;padding:1rem;position:relative;overflow:hidden}}
.card::before{{content:"";position:absolute;top:0;left:0;right:0;height:2px;background:var(--ac)}}
.card.g::before{{background:var(--gn)}}.card.r::before{{background:var(--rd)}}.card.y::before{{background:var(--yw)}}
.num{{font-size:1.6rem;font-weight:800}}.lbl{{font-size:.72rem;color:var(--mu);margin-top:.1rem}}
.cb{{background:var(--cd);border:1px solid var(--bd);border-radius:8px;overflow:hidden;margin-bottom:1rem}}
.cb img{{width:100%;height:auto;display:block}}
.sb{{background:rgba(124,111,255,.07);border:1px solid rgba(124,111,255,.2);border-radius:8px;padding:1rem 1.25rem;margin-bottom:1.5rem;font-size:.88rem;line-height:1.7}}
.dtag{{display:inline-block;padding:.2rem .6rem;border-radius:4px;font-size:.72rem;font-weight:700;background:rgba(61,232,176,.12);color:var(--gn);margin-bottom:.5rem}}
table{{width:100%;border-collapse:collapse;font-size:.8rem}}
th{{background:var(--sf);padding:.5rem .75rem;text-align:left;color:var(--mu);border-bottom:1px solid var(--bd)}}
td{{padding:.5rem .75rem;border-bottom:1px solid var(--bd)}}
tr:last-child td{{border-bottom:none}}
footer{{text-align:center;padding:1.5rem;color:var(--mu);font-size:.75rem;border-top:1px solid var(--bd);margin-top:2rem}}
</style></head><body>
<header>
  <div><div class="logo">Insight <span>Flow</span></div><div class="by">by Aadhya</div></div>
  <div class="meta">Generated {now}<br/>Analysis: {at.upper()} · Domain: {self.domain}</div>
</header>
<main>
<h2>📊 Executive Summary</h2>
<div class="dtag">🏷 {self.domain} Domain</div>
{ov}
<div class="grid">
  <div class="card {sc_cls}"><div class="num">{score}</div><div class="lbl">Data Quality</div></div>
  <div class="card"><div class="num">{sc.get('rows_after',0):,}</div><div class="lbl">Clean Rows</div></div>
  <div class="card"><div class="num">{sc.get('dupes_removed',0):,}</div><div class="lbl">Dupes Removed</div></div>
  <div class="card"><div class="num">{anom.get('total',0)}</div><div class="lbl">Alerts</div></div>
  <div class="card g"><div class="num">{tv:,.0f}</div><div class="lbl">Total {ml}</div></div>
  <div class="card {mom_cls}"><div class="num">{am:+.1f}%</div><div class="lbl">Avg MoM Growth</div></div>
</div>
<h2>📈 KPI Trends</h2>{ks2}{kpi_charts if kpi_charts else '<p style="color:var(--mu)">No KPI charts available.</p>'}
<h2>📊 {at.upper()} Analysis</h2>{as2}{an_charts if an_charts else '<p style="color:var(--mu)">No analysis charts available.</p>'}
<h2>🚨 Anomaly Alerts ({anom.get('total',0)})</h2>{ano}{alerts_html}
</main>
<footer>Insight Flow · by Aadhya · {now}</footer>
</body></html>"""
        self.result["report_html"] = html

    # ── helpers ───────────────────────────────────────────────────────────────

    def _safe_chart(self, fn, *args, **kwargs):
        """Call a chart function; return None instead of raising on any error."""
        if not _MPL_OK:
            return None
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            self.log.warning("Chart %s failed: %s", fn.__name__, e)
            return None

    def _fig_b64(self, fig) -> str:
        buf = io.BytesIO()
        try:
            fig.savefig(buf, format="png", dpi=85, bbox_inches="tight",
                        facecolor=fig.get_facecolor())
            buf.seek(0)
            return base64.b64encode(buf.read()).decode()
        finally:
            plt.close(fig)

    def _df_json(self, df) -> list:
        d = df.copy()
        for c in d.select_dtypes("datetime64").columns:
            d[c] = d[c].astype(str)
        return d.fillna(0).round(3).to_dict("records")

    @staticmethod
    def get_available_analysis_types() -> List[str]:
        return ["kpi"] + list(InsightFlowEngine._DISPATCH.keys())


# backward compat alias
PulseBoardEngine = InsightFlowEngine
