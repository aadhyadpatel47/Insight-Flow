"""
Insight Flow — by Aadhya
Vercel-compatible FastAPI app.
Run locally:  python app.py
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging, sys, os
from pathlib import Path
import io, math, uvicorn, asyncio

app = FastAPI(title="Insight Flow", version="4.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
INDEX_PATHS = [
    BASE_DIR / "template" / "index.html",
    BASE_DIR / "templates" / "index.html",
    BASE_DIR / "index.html",
]


def get_engine():
    from engine import InsightFlowEngine
    return InsightFlowEngine


def _json_safe(value: Any) -> Any:
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


# ── Pydantic models ───────────────────────────────────────────────────────────

class AnalysisTypesResponse(BaseModel):
    types: List[str]


class ColumnInfo(BaseModel):
    all: List[str]
    numeric: List[str]
    date: List[str]
    id: List[str]


class AnalysisResponse(BaseModel):
    filename: str
    analysis_type: str
    domain: str
    date_col: Optional[str] = None
    metric_col: Optional[str] = None
    quality_scorecard: Optional[Dict[str, Any]] = None
    detected: Optional[Dict[str, Any]] = None
    col_stats: Optional[List[Dict[str, Any]]] = None
    preview: Optional[Dict[str, Any]] = None
    kpi: Optional[Dict[str, Any]] = None
    anomalies: Optional[Dict[str, Any]] = None
    ai_summaries: Optional[Dict[str, Any]] = None
    report_html: Optional[str] = None
    audit: Optional[List[str]] = None
    rfm: Optional[Dict[str, Any]] = None
    cohort: Optional[Dict[str, Any]] = None
    funnel: Optional[Dict[str, Any]] = None
    ops: Optional[Dict[str, Any]] = None
    seasonal: Optional[Dict[str, Any]] = None
    trend: Optional[Dict[str, Any]] = None
    pareto: Optional[Dict[str, Any]] = None
    price: Optional[Dict[str, Any]] = None
    growth: Optional[Dict[str, Any]] = None
    contribution: Optional[Dict[str, Any]] = None
    velocity: Optional[Dict[str, Any]] = None
    period: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def index(request: Request):
    for p in INDEX_PATHS:
        if p.exists():
            return Response(p.read_text(encoding="utf-8"), media_type="text/html")
    return Response(
        "<!doctype html><title>Insight Flow</title><h1>index.html missing</h1>"
        "<p>Place index.html in the template/ folder.</p>",
        media_type="text/html",
        status_code=500,
    )


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "4.0.0"}


@app.get("/analysis_types", response_model=AnalysisTypesResponse)
async def get_analysis_types():
    E = get_engine()
    return AnalysisTypesResponse(types=E.get_available_analysis_types())


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    analysis_type: str = Form("kpi"),
    date_col: str = Form(""),
    metric_col: str = Form(""),
    customer_col: str = Form(""),
):
    filename = file.filename or "upload"
    try:
        contents = await file.read()
        ext = Path(filename).suffix.lower()

        def run_engine():
            E = get_engine()
            engine = E(
                contents, ext,
                analysis_type=analysis_type,
                date_col=date_col or None,
                metric_col=metric_col or None,
                customer_col=customer_col or None,
            )
            result = engine.run()
            result["filename"] = filename
            if not result.get("report_html"):
                result["report_html"] = ""
            return result

        result = await asyncio.to_thread(run_engine)
        return JSONResponse(_json_safe(result))

    except Exception as e:
        logger.exception("Upload error for %s", filename)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export")
async def export_csv(file: UploadFile = File(...)):
    filename = file.filename or "upload"
    try:
        contents = await file.read()
        ext = Path(filename).suffix.lower()

        def _run():
            E = get_engine()
            engine = E(contents, ext)
            engine._load()
            engine._clean()
            buf = io.StringIO()
            engine.df.to_csv(buf, index=False)
            buf.seek(0)
            return buf.getvalue()

        csv_data = await asyncio.to_thread(_run)
        return StreamingResponse(
            io.BytesIO(csv_data.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=cleaned_{filename}"},
        )
    except Exception as e:
        logger.exception("Export error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/columns", response_model=ColumnInfo)
async def get_columns(file: UploadFile = File(...)):
    filename = file.filename or "upload"
    try:
        contents = await file.read()
        ext = "." + filename.rsplit(".", 1)[-1].lower()

        def _run():
            E = get_engine()
            engine = E(contents, ext)
            engine._load()
            cols = list(engine.df.columns)
            num_cols = engine.df.select_dtypes(include="number").columns.tolist()
            date_cols = [c for c in cols if any(k in c.lower() for k in ["date", "time", "dt", "period", "month", "year"])]
            id_cols = [c for c in cols if any(k in c.lower() for k in ["customer", "user", "client", "id"])]
            return {"all": cols, "numeric": num_cols, "date": date_cols, "id": id_cols}

        result = await asyncio.to_thread(_run)
        return result
    except Exception as e:
        logger.exception("Columns error")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    uvicorn.run("app:app", host=host, port=port, reload=False)
