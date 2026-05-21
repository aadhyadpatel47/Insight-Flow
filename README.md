# InsightFlow
### Business Analysis Engine — by Aadhya

> Upload any CSV, Excel, or JSON file. Get domain-aware business insights, written narrative summaries, anomaly alerts, and a downloadable HTML report — in seconds.

🔗 **Live:** [insight-flow-rust.vercel.app](https://insight-flow-rust.vercel.app)
📁 **GitHub:** [aadhyadpatel47](https://github.com/aadhyadpatel47)
💼 **LinkedIn:** [aadhyapatel](https://www.linkedin.com/in/aadhyapatel)

---

## What It Does

Most EDA tools tell you what your data looks like. InsightFlow tells you what it means for your business.

It automatically detects whether your dataset belongs to **Sales, Marketing, Finance, HR, Operations, or E-commerce** — then generates domain-specific summaries, chart narratives, and anomaly alerts tailored to that domain.

---

## Analysis Types

| Type | What It Produces |
|------|-----------------|
| **KPI** | Monthly trend line, MoM bar chart, QoQ donut, growth summary |
| **Trend** | Linear regression via NumPy polyfit, R² fit score, histogram, box plot |
| **RFM** | Customer segmentation — Champions / Loyal / At-Risk / Needs Attention / Lost — donut + scatter + bar |
| **Cohort** | AOV and revenue per cohort month — bar and line charts |
| **Funnel** | Stage-by-stage conversion rates — bar and drop-off line chart |
| **Ops** | 7-day and 30-day moving averages with Bollinger-band style bounds |
| **Seasonal** | Month / Quarter / Year / Day-of-Week breakdown — 4-panel chart |
| **Pareto** | 80/20 rule — categories driving 80% of value — pie + cumulative chart |
| **Growth Accounting** | New vs Retained vs Churned customers per period — stacked + net bar |
| **Period Comparison** | Year-over-year monthly comparison — grouped bar and multi-line chart |
| **Velocity** | Rate of change and acceleration — 3-panel chart with leading indicators |
| **Contribution** | Segment-level value drivers — bar with % labels and pie chart |
| **Price Sensitivity** | Price vs demand correlation with scatter and trend |

KPI analysis and Anomaly Detection always run regardless of which type is selected.

---

## Domain Detection

InsightFlow scores column names against domain keyword lists and auto-assigns the best-fit domain. Minimum threshold of 2 keyword matches required — defaults to "General" if no domain scores high enough.

| Domain | Keywords Checked |
|--------|-----------------|
| **Sales** | revenue, sales, order, deal, quota, pipeline, invoice, discount, product, sku, unit_price |
| **Marketing** | campaign, ctr, impression, click, conversion, lead, mql, sql, channel, source, utm, spend, roas, cpc |
| **Finance** | profit, margin, cost, expense, budget, forecast, cash, ebitda, opex, capex, balance, asset, liability |
| **HR** | employee, headcount, attrition, salary, tenure, hire, departure, department, role, team, engagement |
| **Operations** | ticket, sla, handle_time, utilization, queue, backlog, throughput, ops, incident, resolution |
| **E-commerce** | cart, checkout, basket, refund, return, sku, category, rating, review, shipping |

---

## Data Cleaning — 10 Automated Rules

| Rule | What It Does |
|------|-------------|
| R01 | Drop fully duplicate rows |
| R02 | Strip leading / trailing whitespace from strings |
| R03 | Standardise column names — lowercase, underscores, remove special characters |
| R04 | Drop columns with more than 90% empty values |
| R05 | Fill numeric nulls with column median |
| R06 | Fill categorical nulls with "Unknown" |
| R07 | Parse date/time columns using smart detection — avoids misidentifying numeric or ID columns |
| R08 | Remove currency symbols (₹, $, £) and commas from numeric strings |
| R09 | Flag outliers beyond 3× IQR in a separate boolean column |
| R10 | Deduplicate on detected ID/key columns (id, key, uid, ref) |

A quality score (0–100) is calculated from null rate and duplicate rate and shown in the dashboard.

---

## Anomaly Detection

Two methods run on every upload:

- **Z-score outliers** — flags values beyond threshold on numeric columns
- **Period drop alerts** — flags significant MoM drops in the metric column
- **High null rate** — warns when columns exceed null thresholds post-cleaning

Each alert includes: type, severity, column name, description, and Z-score where applicable.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the frontend (Jinja2 template) |
| `GET` | `/health` | Status check — returns version and app name |
| `GET` | `/analysis_types` | Returns list of all available analysis types |
| `POST` | `/upload` | Upload file → full analysis JSON response |
| `POST` | `/export` | Upload file → cleaned CSV download (streamed, never saved to disk) |
| `POST` | `/columns` | Upload file → column name suggestions for dropdowns |

All file handling is in-memory. No file is ever written to disk.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI |
| Data Processing | Pandas, NumPy |
| Charts | Matplotlib — server-rendered PNG, embedded as base64 |
| Frontend | Vanilla HTML, CSS, JavaScript — no framework, no build step |
| Templates | Jinja2 (index.html served from `templates/` folder) |
| Deployment | Vercel (`@vercel/python`, Python 3.11 pinned) |

No React. No bundler. No external chart CDN.

---

## Project Structure

```
insightflow/
├── app.py              ← FastAPI server — routes, Pydantic models, report CSS injection
├── engine.py           ← Analysis engine — cleaning, 13 analysis types, charts, summaries
├── requirements.txt    ← Python dependencies
├── vercel.json         ← Vercel config — Python 3.11 pinned
└── templates/
    └── index.html      ← Full frontend — served by Jinja2
```

---

## Run Locally

```bash
# 1. Clone
git clone https://github.com/aadhyadpatel47/insightflow.git
cd insightflow

# 2. Create virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start server
python app.py

# 5. Open browser
# http://localhost:5000
```

Supported file formats: `.csv`, `.xlsx`, `.xls`, `.json`

---

## Deploy to Vercel

```bash
npm install -g vercel
vercel login
vercel --prod
```

`vercel.json` is pre-configured with Python 3.11 and routes all traffic through `app.py`.

---

## Requirements

```
fastapi
uvicorn
pandas
numpy
matplotlib
Jinja2
python-multipart
pydantic
```

Python 3.11 required. The `str | None` union syntax and several pandas resample aliases depend on it.

---

## Known Limitations

- Files above 50 MB may be slow on Vercel's free tier due to pandas processing time
- Visualization sampling activates above 50,000 rows — full data still used for calculations
- RFM requires customer ID, date, and a monetary value column
- Cohort analysis requires at least one datetime column
- Funnel analysis works best with a dedicated stage or status column
- Written summaries are heuristic-based — not LLM-generated

---

## Roadmap

- [ ] PDF report export
- [ ] SQL database direct connectivity
- [ ] Predictive forecasting (ARIMA / Prophet)
- [ ] LLM-powered narrative generation (Claude API)
- [ ] Saved sessions with user authentication
- [ ] Scheduled report generation and email delivery
- [ ] Real-time dashboards via WebSocket
- [ ] Multi-user collaboration

---

## Author

**Aadhya Patel** — BBA Business Analytics, Ganpat University

[![GitHub](https://img.shields.io/badge/GitHub-aadhyadpatel47-181717?logo=github)](https://github.com/aadhyadpatel47)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-aadhyapatel-0A66C2?logo=linkedin)](https://www.linkedin.com/in/aadhyapatel)

---

MIT License
