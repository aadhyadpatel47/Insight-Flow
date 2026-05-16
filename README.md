# InsightFlow — Business Analysis Engine
### by Aadhya

> Upload any CSV or Excel file. Get domain-aware business insights, written narrative summaries, anomaly alerts, and a downloadable report — all in seconds.

🔗 **Live Demo:** `insight-flow-rust.vercel.app`
📁 **GitHub:** [aadhyadpatel47](https://github.com/aadhyadpatel47)
💼 **LinkedIn:** [aadhyapatel](https://www.linkedin.com/in/aadhyapatel)

---

## What Makes InsightFlow Different

Most EDA tools tell you *what* your data looks like. InsightFlow tells you *what it means for your business.*

It automatically detects whether your dataset belongs to **Sales, Marketing, Finance, or HR** — and generates domain-specific written summaries, recommendations, and alerts for each analysis.

---

## Feature Overview

| Feature | Details |
|---------|---------|
| 📈 **KPI Trend Analysis** | Monthly, QoQ, and YoY growth with trend line, MoM bars, and donut chart |
| 📉 **Trend Analysis** | Linear regression, R² fit, histogram, and box plot |
| 🎯 **RFM Segmentation** | Champions / Loyal / At-Risk / Needs Attention / Lost — donut + scatter + bar |
| 🔽 **Funnel Analysis** | Stage-by-stage conversion rates with bar and line drop-off charts |
| 👥 **Cohort Analysis** | AOV and total revenue per cohort month — bar and line |
| ⚙️ **Ops Monitoring** | 7-day and 30-day moving averages with Bollinger-band style bounds |
| 🌦 **Seasonal Patterns** | Month / Quarter / Year / Day-of-Week breakdown — 4-panel chart |
| 📊 **Pareto Analysis** | 80/20 rule — which categories drive 80% of value, with pie + cumulative chart |
| 🔄 **Growth Accounting** | New vs Retained vs Churned customers per period — stacked and net bar charts |
| 📅 **Period Comparison** | Year-over-year monthly comparison — grouped bar and multi-line chart |
| ⚡ **Velocity Tracking** | Rate of change and acceleration — 3-panel chart with leading indicators |
| 🧩 **Contribution Analysis** | Which segments drive the most value — bar with % labels and pie chart |
| 🚨 **Anomaly Detection** | Z-score + period drop alerts with plain-English descriptions |
| ✍️ **Written Summaries** | Auto-generated narrative for every analysis section with domain-specific insight |
| 🧹 **Data Cleaning** | 10 automated rules: nulls, duplicates, type parsing, currency cleaning, outlier flags |
| 📄 **HTML Report** | One-click download — embeds all charts, summaries, and alerts |
| 🌙 **Dark / Light Mode** | Persisted to localStorage |
| 📊 **1 Lakh+ Rows** | Intelligent sampling for charts, full data used for analysis |

---

## Domain Detection

InsightFlow automatically identifies your data domain from column names:

| Domain | Detected From |
|--------|--------------|
| **Sales** | revenue, order, product, discount, quantity, price, invoice |
| **Marketing** | campaign, lead, click, impression, conversion, channel, funnel, MQL |
| **Finance** | profit, expense, cost, budget, margin, tax, asset, cash, balance |
| **HR** | employee, salary, department, attrition, hire, tenure, performance |

Written summaries, recommendations, and chart titles adapt to the detected domain automatically.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI |
| Data Processing | Pandas, NumPy, SciPy |
| Charts | Matplotlib, Seaborn — server-rendered PNG, embedded as base64 |
| Frontend | Vanilla HTML, CSS, JavaScript — no build step, no framework |
| Deployment | Vercel (backend API) + GitHub Pages (frontend) |

No React. No bundler. No external chart CDN required for reports.

---

## How It Works

### 1. Upload
File is sent to `/upload` via multipart form data. Supported formats: CSV, Excel (.xlsx / .xls), JSON.

### 2. Data Processing
`engine.py` runs automatically in one pass:
- Detects business domain from column names
- Identifies date, metric, and customer ID columns
- Applies 10 cleaning rules (nulls, duplicates, whitespace, currency symbols, outlier flags)
- Standardises column names and data types

### 3. Analysis Pipeline
The selected analysis type runs and generates:
- KPI metrics and growth rates
- All charts (trend, bars, donut, scatter, histogram, box plot, line, pie — depending on type)
- Anomaly alerts with Z-score and period-drop detection
- Domain-specific written narrative with headlines, sections, and recommendations

### 4. JSON Response
Everything comes back as one JSON object — no second requests needed for most views. This enables instant dashboard rendering on the frontend.

### 5. Frontend Rendering
The frontend builds the full dashboard from the JSON:
- Summary KPI cards
- Analysis tabs (KPI, Analysis, Alerts, Quality, Preview)
- Charts rendered from base64-encoded PNGs
- Written summary sections with headings and paragraphs
- Alert banners with severity levels

### 6. Export
- **Clean CSV** — cleaned dataset downloadable directly from the browser
- **HTML Report** — standalone offline file with all charts embedded, opens in any browser

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the frontend |
| `GET` | `/health` | Status and version check |
| `POST` | `/upload` | Upload file → full analysis JSON |
| `POST` | `/export` | Upload file → cleaned CSV download |
| `POST` | `/columns` | Upload file → column names for dropdowns |

---

## Run Locally

```bash
# 1. Clone the repo
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

# 4. Start the server
python app.py

# 5. Open in browser
# http://localhost:5000
```

---

## Deploy to Vercel

```bash
npm install -g vercel
vercel login
vercel --prod
```

`vercel.json` is pre-configured. Vercel auto-detects the FastAPI app from `app.py`.

---

## Deploy Frontend to GitHub Pages

1. Copy `templates/index.html` (or the embedded HTML from `app.py`) to your GitHub Pages repo
2. Update the `API_BASE` variable at the top of the script section:

```javascript
const API_BASE = window.location.hostname === 'aadhyadpatel47.github.io'
  ? 'https://your-vercel-app.vercel.app'  // ← your Vercel deployment URL
  : '';
```

3. Push to your GitHub Pages branch. The frontend calls the Vercel backend for all API requests.

---

## Project Structure

```
insightflow/
├── app.py              ← FastAPI server — all routes, HTML served from here
├── engine.py           ← Full analysis engine — cleaning, 12 analysis types, charts, summaries
├── requirements.txt    ← Python dependencies
├── vercel.json         ← Vercel deployment config
├── Procfile            ← Fallback for Render / Railway
└── README.md
```

---

## Data Cleaning Rules

| Rule | What It Does |
|------|-------------|
| R01 | Drop fully duplicate rows |
| R02 | Strip leading / trailing whitespace from strings |
| R03 | Standardise column names (lowercase, underscores) |
| R04 | Drop columns with >90% empty values |
| R05 | Fill numeric nulls with column median |
| R06 | Fill categorical nulls with "Unknown" |
| R07 | Parse date/time columns to datetime dtype |
| R08 | Remove currency symbols (₹, $, £) and commas from numeric strings |
| R09 | Flag outliers beyond 3 IQR in a separate boolean column |
| R10 | Deduplicate on detected ID/key columns |

---

## Known Limitations

- Files above 50 MB may be slow on free-tier hosting due to pandas processing time
- Funnel analysis works best with a dedicated stage or status column
- Cohort analysis requires at least one datetime column
- RFM requires customer ID, date, and monetary value columns
- Written summaries are heuristic-based — not LLM-generated
- Visualization sampling kicks in above 50,000 rows for chart performance

---

## Roadmap

- [ ] SQL database connectivity (direct query support)
- [ ] PDF export for reports
- [ ] Predictive forecasting (ARIMA / Prophet integration)
- [ ] Real-time dashboards via WebSocket
- [ ] Saved analysis sessions with user authentication
- [ ] Automated ML recommendations
- [ ] Multi-user collaboration and sharing
- [ ] Scheduled report generation and email delivery
- [ ] LLM-powered narrative generation (GPT / Claude API integration)

---

## Author

**Aadhya Patel** — BBA Business Analytics, Ganpat University

[![GitHub](https://img.shields.io/badge/GitHub-aadhyadpatel47-181717?logo=github)](https://github.com/aadhyadpatel47)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-aadhyapatel-0A66C2?logo=linkedin)](https://www.linkedin.com/in/aadhyapatel)

---

## License

MIT License — free to use, modify, and distribute.
