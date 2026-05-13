# Insight Flow — AI Business Intelligence Studio

Upload any CSV, Excel, or JSON file. Get an AI-powered business intelligence dashboard with narratives in seconds.

🔗 Live Demo: [your-insight-flow-backend.vercel.app](https://your-insight-flow-backend.vercel.app)

---

# Overview

Insight Flow is a full-stack business intelligence and automated analytics platform built with FastAPI and vanilla JavaScript.

The system automatically:
- detects business domains
- cleans messy datasets
- runs advanced analytical models
- generates AI-style business narratives
- creates downloadable offline reports

—all with zero configuration required.

Designed for analysts, students, startups, and business teams who want rapid insights without manual setup.

---

# Features

## 🏷 Auto Domain Detection
Automatically identifies:
- Sales
- Marketing
- Finance
- HR
- Operations
- E-commerce

using intelligent column pattern recognition.

---

## 🧹 Intelligent Data Cleaning Engine

Applies a 10-rule preprocessing pipeline:

- Currency symbol stripping
- Date parsing
- Null handling
- Duplicate removal
- Type conversion
- Outlier detection
- Column normalization
- Missing-value imputation
- Invalid row filtering
- Data consistency checks

---

# 📈 Advanced Analysis Models

Insight Flow supports 13 built-in analytical engines:

| Analysis Type | Description |
|---|---|
| KPI Trends | Performance tracking over time |
| RFM Segmentation | Customer behavior segmentation |
| Cohort Analysis | Retention and repeat behavior |
| Funnel Analysis | Conversion stage monitoring |
| Pareto 80/20 | Revenue concentration analysis |
| Trend Analysis | Growth and movement detection |
| Seasonal Patterns | Seasonality identification |
| Operations Monitoring | Operational metric tracking |
| Price Sensitivity | Pricing behavior analysis |
| Growth Accounting | Revenue/user growth attribution |
| Contribution Margin | Profitability insights |
| Velocity Tracking | Speed and efficiency metrics |
| Period Comparison | Comparative performance analysis |

---

# 💬 AI Narratives

Instead of only showing charts and numbers, Insight Flow generates plain-English summaries explaining:

- what changed
- why it matters
- possible business implications
- key opportunities or risks

Example:
> “Revenue grew 18% month-over-month, driven primarily by repeat customers in the electronics category.”

---

# 🚨 Smart Alerts & Anomaly Detection

Automatically flags:
- Z-score anomalies
- sudden drops greater than 20%
- high null-rate columns
- unstable trends
- abnormal spikes

---

# 📊 Rich Visualizations

Auto-generated visual outputs include:

- Donut Charts
- Scatter Plots
- Heatmaps
- Box Plots
- Trend Lines
- Bollinger Bands
- KPI Cards
- Distribution Graphs

Built using:
- Matplotlib
- Chart.js

---

# 📄 Standalone Offline Report

Generate a fully downloadable HTML report containing:

- all visualizations
- executive summaries
- anomaly alerts
- business narratives
- dark-mode styling

No internet connection required after export.

---

# ⚡ High-Performance FastAPI Backend

- Async FastAPI architecture
- Thread-pooled Pandas processing
- Optimized JSON payload generation
- Single-pass analysis pipeline
- Minimal frontend latency

Large datasets are sampled intelligently for rendering performance.

---

# 🌓 Dark / Light Mode

- Space-themed modern UI
- Persistent theme storage via `localStorage`
- Responsive layout for desktop and mobile

---

# 🗃 Large File Support

Supports:
- CSV
- XLSX
- XLS
- JSON

Capable of handling datasets with:
- 1M+ rows for processing
- optimized 50k-row visualization sampling

---

# Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| Data Processing | Pandas, NumPy, SciPy |
| Visualization Engine | Matplotlib |
| Frontend Charts | Chart.js 4.4 |
| Frontend | Vanilla HTML, CSS, JavaScript |
| File Support | CSV, XLSX, XLS, JSON |
| Deployment | Render, Railway, Vercel |

---

# Design Philosophy

Insight Flow is intentionally built without heavy frontend frameworks.

Benefits:
- lightweight deployment
- faster load times
- zero build complexity
- easier hosting
- simplified debugging

No React. No bundlers. No build pipeline.

---

# Project Structure

```text
insight-flow/
├── app.py
├── engine.py
├── requirements.txt
├── vercel.json
├── Procfile
└── README.md

# How It Works

## 1. Upload

Files are uploaded to the `/upload` endpoint using multipart form data.

---

## 2. Data Processing

`engine.py` automatically:

- Detects the business domain
- Identifies key columns
- Cleans and validates the dataset
- Standardizes formats
- Prepares analytical metrics

---

## 3. Analysis Pipeline

The selected analysis engine runs in a single pass and generates:

- KPI metrics
- Visual charts
- Anomaly alerts
- Statistical summaries
- AI-powered narrative insights

---

## 4. JSON Response

All processed results are returned as one optimized JSON payload.

This minimizes repeated API calls and enables fast dashboard rendering.

---

## 5. Frontend Rendering

The frontend instantly generates:

- KPI cards
- Interactive dashboards
- Analytical tabs
- Charts and visualizations
- Summary panels
- Alert banners

using the returned JSON object.

---

## 6. Export

The processed dataset can be:

- Exported as a cleaned CSV file
- Downloaded as a standalone offline HTML report

---

# API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves the frontend |
| `/upload` | POST | Upload file and return analysis JSON |
| `/export` | POST | Export cleaned CSV |
| `/columns` | POST | Read file headers for dynamic dropdowns |
| `/health` | GET | Health and status check |

---

# Deployment

Insight Flow can be deployed on:

- Render
- Railway
- Vercel

### Recommended Setup

- **Backend** → Render / Railway
- **Frontend** → Vercel or GitHub Pages

---

# Known Limitations

- Very large files (>50MB) may require additional processing time.
- Data processing is CPU-intensive due to heavy Pandas operations.
- Funnel analysis performs best with dedicated stage/status columns.
- AI narratives are heuristic-based and not LLM-generated.
- Visualization sampling is applied for extremely large datasets.

---

# Future Roadmap

Planned enhancements include:

- SQL database connectivity
- Real-time dashboards
- User authentication
- Saved analysis sessions
- PDF export support
- Predictive forecasting
- Automated ML recommendations
- Multi-user collaboration
- Scheduled report generation

---

# Screenshots

## Dashboard
_Add dashboard screenshot here_

---

## KPI Analysis
_Add KPI analysis screenshot here_

---

## AI Narrative Panel
_Add AI narrative screenshot here_

---

## Dark Mode
_Add dark mode screenshot here_

---

# Author

## Aadhya

- GitHub: https://github.com/aadhyadpatel47
- LinkedIn: https://www.linkedin.com/in/aadhyapatel

---

# License

MIT License

Free to use, modify, and distribute.
---

