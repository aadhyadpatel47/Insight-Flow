"""
Insight Flow — by Aadhya
Run:  python main.py
Open: http://localhost:5000

Refactoring applied:
  1. Serves index.html via Jinja2Templates at GET /
  2. Pydantic BaseModel response contracts on all data endpoints
  3. All heavy Pandas/Matplotlib work offloaded with asyncio.to_thread()
  4. Uploaded files read into BytesIO — never saved to disk
  5. ThreadPoolExecutor removed; asyncio.to_thread handles thread management
  6. scipy / colorama / xlsxwriter removed from imports (not in requirements)
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging, sys
from pathlib import Path
import io, math, traceback, uvicorn, asyncio
from engine import InsightFlowEngine

app = FastAPI(title="Insight Flow", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Configure logging for the application
logging.basicConfig(
    level=logging.INFO, # Set to INFO for production, DEBUG for development
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout) # Log to stdout, which is standard for containerized apps
    ]
)
logger = logging.getLogger(__name__)
# FIX: Serve index.html via Jinja2Templates — required by spec
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
INDEX_PATHS = [
    BASE_DIR / "index.html",
    BASE_DIR / "templates" / "index.html",
]

# New Pydantic model for the list of analysis types
class AnalysisTypesResponse(BaseModel):
    types: List[str]


def _json_safe(value: Any) -> Any:
    """Convert pandas/numpy output into strict JSON-safe Python values."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value

# ── Pydantic response models ──────────────────────────────────────────────────

class ColumnInfo(BaseModel):
    all: List[str]
    numeric: List[str]
    date: List[str]
    id: List[str]


class QualityScorecard(BaseModel):
    rows_before:   int
    rows_after:    int
    cols:          int
    nulls_before:  int
    nulls_after:   int
    dupes_removed: int
    quality_score: float
    dropped_cols:  List[str]


class DetectedColumns(BaseModel):
    date_col:     Optional[str]
    metric_col:   Optional[str]
    customer_col: Optional[str]
    total_rows:   int
    total_cols:   int
    columns:      List[str]


class AnalysisResponse(BaseModel):
    filename:          str
    analysis_type:     str
    domain:            str
    date_col:          Optional[str]
    metric_col:        Optional[str]
    quality_scorecard: Optional[Dict[str, Any]]
    detected:          Optional[Dict[str, Any]]
    col_stats:         Optional[List[Dict[str, Any]]]
    preview:           Optional[Dict[str, Any]]
    kpi:               Optional[Dict[str, Any]]
    anomalies:         Optional[Dict[str, Any]]
    ai_summaries:      Optional[Dict[str, Any]]
    report_html:       Optional[str]
    audit:             Optional[List[str]]
    # Analysis-type specific keys (present depending on analysis_type)
    rfm:          Optional[Dict[str, Any]] = None
    cohort:       Optional[Dict[str, Any]] = None
    funnel:       Optional[Dict[str, Any]] = None
    ops:          Optional[Dict[str, Any]] = None
    seasonal:     Optional[Dict[str, Any]] = None
    trend:        Optional[Dict[str, Any]] = None
    pareto:       Optional[Dict[str, Any]] = None
    price:        Optional[Dict[str, Any]] = None
    growth:       Optional[Dict[str, Any]] = None
    contribution: Optional[Dict[str, Any]] = None
    velocity:     Optional[Dict[str, Any]] = None
    period:       Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"   # tolerate any extra keys the engine may add


# ── Report CSS (injected into downloaded HTML reports) ────────────────────────
REPORT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;1,300;1,400&family=Outfit:wght@300;400;500&family=DM+Mono:wght@300;400&display=swap');

:root {
  --bg: #f8fafc;
  --s1: #ffffff;
  --s2: #f1f5f9;
  --b1: #cbd5e1;
  --t1: #000000;
  --t2: #000000;
  --t3: #000000;
  --acc: #4f46e5;
  --acc-bg: rgba(79, 70, 229, 0.05);
  --acc-border: rgba(79, 70, 229, 0.2);
  --up: #059669;
  --dn: #dc2626;
  --warn: #d97706;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  color: var(--t1);
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
  line-height: 1.6;
}

header {
  padding: 2.5rem 2rem;
  border-bottom: 1px solid var(--b1);
  background: var(--s1);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.logo {
  font-family: 'Cormorant Garamond', serif;
  font-size: 28px;
  font-weight: 400;
  color: var(--t1);
}
.logo span { color: var(--acc); font-style: italic; }

.by { font-size: 14px; color: var(--t3); font-style: italic; margin-top: 4px; font-family: 'Cormorant Garamond', serif; }

.meta {
  text-align: right;
  font-family: 'DM Mono', monospace;
  font-size: 11px;
  color: var(--t3);
  line-height: 1.5;
}

main {
  max-width: 960px;
  margin: 0 auto;
  padding: 4rem 2rem;
}

h2 {
  font-family: 'Cormorant Garamond', serif;
  font-size: 26px;
  font-weight: 400;
  margin: 4rem 0 1.5rem;
  color: var(--t1);
  border-bottom: 1px solid var(--b1);
  padding-bottom: 0.75rem;
}

.domain-tag {
  display: inline-block;
  padding: 6px 14px;
  border-radius: 4px;
  background: var(--acc-bg);
  color: var(--acc);
  border: 1px solid var(--acc-border);
  font-family: 'DM Mono', monospace;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 1.5rem;
}

.summary-box {
  background: var(--acc-bg);
  border-left: 4px solid var(--acc);
  padding: 2rem;
  margin-bottom: 2.5rem;
  font-style: italic;
  font-size: 16px;
  color: var(--t2);
  border-radius: 0 8px 8px 0;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 4rem;
}

.card {
  background: var(--s1);
  border: 1px solid var(--b1);
  padding: 2rem;
  border-radius: 12px;
  text-align: center;
}

.num {
  font-family: 'Cormorant Garamond', serif;
  font-size: 42px;
  font-weight: 300;
  margin-bottom: 0.5rem;
  color: var(--t1);
  line-height: 1;
}

.lbl {
  font-family: 'DM Mono', monospace;
  font-size: 10px;
  color: var(--t3);
  text-transform: uppercase;
  letter-spacing: 0.15em;
}

.card.g .num { color: var(--up); }
.card.r .num { color: var(--dn); }
.card.y .num { color: var(--warn); }

.chart-block {
  margin-bottom: 2.5rem;
  border: 1px solid var(--b1);
  border-radius: 12px;
  background: #fff;
  padding: 1.5rem;
}

.chart-block img {
  width: 100%;
  height: auto;
  display: block;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 1.5rem 0 3rem;
  border-radius: 8px;
  overflow: hidden;
}

th {
  text-align: left;
  padding: 14px 16px;
  background: #f8fafc;
  font-family: 'DM Mono', monospace;
  font-size: 11px;
  color: var(--t3);
  text-transform: uppercase;
  border-bottom: 2px solid var(--b1);
}

td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--b1);
  font-family: 'DM Mono', monospace;
  font-size: 13px;
  color: var(--t2);
}

tr:last-child td { border-bottom: none; }

footer {
  text-align: center;
  padding: 4rem 2rem;
  border-top: 1px solid var(--b1);
  color: var(--t3);
  font-family: 'DM Mono', monospace;
  font-size: 12px;
  letter-spacing: 0.05em;
}
</style>
"""

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serves the main index.html page with available analysis types."""
    for template_path in INDEX_PATHS:
        if template_path.exists():
            return Response(template_path.read_text(encoding="utf-8"), media_type="text/html")
    available_types = InsightFlowEngine.get_available_analysis_types()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"analysis_types": available_types} # Pass to template
    )

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/analysis_types", response_model=AnalysisTypesResponse)
async def get_analysis_types():
    """Returns a list of all available analysis types for dropdowns."""
    types = InsightFlowEngine.get_available_analysis_types()
    return AnalysisTypesResponse(types=types)

@app.get("/health")
async def health():
    return {"status": "ok", "name": "Insight Flow", "version": "3.0.0", "by": "Aadhya"}


@app.post("/upload", response_model=AnalysisResponse)
async def upload(
    file: UploadFile = File(...),
    analysis_type: str = Form("kpi"),
    date_col: str = Form(""),
    metric_col: str = Form(""),
    customer_col: str = Form(""),
):
    try:
        # FIX: Read into memory — never save to disk
        contents = await file.read()
        ext      = Path(file.filename).suffix.lower()
        filename = file.filename

        def run_engine():
            engine = InsightFlowEngine(
                contents, ext,
                analysis_type=analysis_type,
                date_col=date_col or None,
                metric_col=metric_col or None,
                customer_col=customer_col or None,
            )
            result = engine.run()
            
            # Defensive: Ensure report_html is always a string if it exists, for frontend compatibility
            if "report_html" in result and result["report_html"] is None:
                result["report_html"] = ""
            result["filename"] = filename
            # Inject polished report CSS into the downloaded HTML
            if result.get("report_html"):
                html  = result["report_html"]
                start = html.find("<style>")
                end   = html.find("</style>") + len("</style>")
                if start != -1 and end != -1:
                    html = html[:start] + REPORT_CSS + html[end:]
                result["report_html"] = html
            return result

        # FIX: Non-blocking — heavy engine work runs in a thread
        result = await asyncio.to_thread(run_engine)
        return JSONResponse(_json_safe(result))

    except Exception as e:
        logger.exception(f"Error processing upload for file {filename}: {e}") # Log the full traceback
        raise HTTPException(status_code=500, detail=f"An internal server error occurred while processing your request. Please try again or contact support. Details: {e}")

@app.post("/export")
async def export_csv(file: UploadFile = File(...)):
    """Clean the uploaded file and stream back a CSV — never touches disk."""
    try:
        # FIX: in-memory read
        contents = await file.read()
        ext      = Path(file.filename).suffix.lower()
        filename = file.filename

        def _run():
            engine = InsightFlowEngine(contents, ext)
            engine._load()
            engine._clean()
            buf = io.StringIO()
            engine.df.to_csv(buf, index=False)
            buf.seek(0)
            return buf.getvalue()

        # FIX: Non-blocking
        csv_data = await asyncio.to_thread(_run)
        return StreamingResponse(
            io.BytesIO(csv_data.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=cleaned_{filename}"}
        )
    except Exception as e: # Catching broad Exception, consider more specific ones if possible
        logger.exception(f"Error exporting CSV for file {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/columns", response_model=ColumnInfo)
async def get_columns(file: UploadFile = File(...)):
    """Inspect uploaded file and return column suggestions — never saves to disk."""
    try:
        # FIX: in-memory read
        contents = await file.read()
        ext      = "." + file.filename.rsplit(".", 1)[-1].lower()

        def _run():
            engine = InsightFlowEngine(contents, ext)
            engine._load()
            cols      = list(engine.df.columns)
            num_cols  = engine.df.select_dtypes(include="number").columns.tolist()
            date_cols = [c for c in cols
                         if any(k in c.lower() for k in ["date","time","dt","period","month","year"])]
            id_cols   = [c for c in cols
                         if any(k in c.lower() for k in ["customer","user","client","id"])]
            return {"all": cols, "numeric": num_cols, "date": date_cols, "id": id_cols}

        # FIX: Non-blocking
        result = await asyncio.to_thread(_run)
        return result

    except Exception as e: # Catching broad Exception, consider more specific ones if possible
        logger.exception(f"Error getting columns for file {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # For production, consider using environment variables for host and port,
    # and running with a process manager like Gunicorn.
    import os
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host=host, port=port)

