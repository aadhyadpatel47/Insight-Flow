### GitHub Repository Name Suggestion
**`insight-flow`** 
*(Clean, professional, and matches your branding perfectly. URL: https://your-insight-flow-backend.vercel.app

***

### `README.md`

```markdown
# Insight Flow — by Aadhya
Upload any CSV, Excel, or JSON file. Get an AI-powered business intelligence dashboard with narratives in seconds.

🔗 *Live Demo: [your-vercel-app.vercel.app]*

## What It Does
Insight Flow is a full-stack business intelligence and data analysis tool built with FastAPI and vanilla JavaScript. Upload any data file and it automatically detects your business domain, cleans your data using a 10-rule engine, runs deep analytical models (RFM, Cohort, Pareto, etc.), and generates plain-English AI narratives — with zero configuration required.

## Features
- **🏷 Auto Domain Detection** — Identifies Sales, Marketing, Finance, HR, Operations, or E-commerce domains automatically
- **🧹 10-Rule Data Cleaning** — Strips currency symbols, parses dates, removes dupes, fills nulls, and flags outliers
- **📈 13 Analysis Types** — KPI Trends, RFM Segmentation, Cohort Analysis, Funnel, Pareto 80/20, Trend Analysis, Seasonal Patterns, Ops Monitoring, Price Sensitivity, Growth Accounting, Contribution Margin, Velocity Tracking, Period Comparison
- **💬 AI Narratives** — Plain-English summaries explain what the numbers mean, not just what they are
- **🚨 Anomaly Alerts** — Z-score anomalies, period drops >20%, and high null-rate detection
- **📊 Rich Visualizations** — Auto-generated Matplotlib charts (donut, scatter, box, heatmap, Bollinger bands)
- **📄 Standalone HTML Report** — Download a fully offline, dark-mode branded report with all charts and summaries
- **⚡ Async FastAPI** — Heavy Pandas processing runs in a thread pool to keep the server responsive
- **🌓 Dark / Light Mode** — Persisted to localStorage with a beautiful space-themed UI
- **🗃 Large File Support** — Handles 1M+ rows via chunked sampling (50k for chart rendering)

## Tech Stack
| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| Data Processing | Pandas, NumPy, SciPy |
| Visualizations | Matplotlib, Seaborn |
| Frontend | Vanilla HTML, CSS, JavaScript |
| Charts (UI) | Chart.js 4.4 |
| File Support | CSV, XLSX, XLS, JSON |
| Deployment | Render / Railway / Vercel (Backend) |

*No React. No build step. No bundler.*

## Project Structure
```text
insight-flow/
├── app.py            # FastAPI routes: /upload, /export, /columns, /health
├── engine.py         # Core engine: cleaning, domain detection, 13 analysis models, AI narratives, HTML report
├── requirements.txt  # Python dependencies
└── README.md         # You are here
```
*(The entire frontend is embedded in `app.py` for a zero-config single-file deployment, just like the original Flask design).*

## Running Locally
```bash
git clone https://github.com/yourusername/insight-flow.git
cd insight-flow
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000

## How It Works
1. File uploads to `/upload` via multipart form data.
2. `engine.py` cleans the data, auto-detects domain and key columns (date, metric, customer).
3. The chosen analysis model runs (KPI, RFM, Pareto, etc.), generating base64 Matplotlib charts, anomaly alerts, and AI summaries in a single pass.
4. Everything comes back as one JSON object — no secondary requests needed for rendering charts.
5. The frontend instantly renders the full dashboard with summary cards, interactive tabs, and AI narrative banners.
6. The standalone HTML report is generated from the same JSON payload and can be downloaded for offline viewing.
7. `/export` applies cleaning rules server-side on the original DataFrame and streams a cleaned CSV back.

## API Endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves the single-page frontend |
| `/upload` | POST | Upload file & analysis settings, returns full analysis JSON |
| `/export` | POST | Applies fixes server-side, returns cleaned CSV |
| `/columns` | POST | Reads file headers for dynamic dropdown population |
| `/health` | GET | API status check |

## Known Limitations
- Data processing is CPU-bound; while `asyncio.to_thread` prevents server blocking, very large files (>50MB) may take a few seconds to process.
- The frontend column dropdown fetches raw file headers before cleaning, though the backend safely auto-syncs them post-cleaning.
- Funnel analysis auto-detects stages by cardinality; for best results, use a dedicated "stage" or "status" column.
- AI narratives are rule-based heuristics (not LLM-generated) for zero-latency offline reporting.

## Author
**Aadhya**
```
