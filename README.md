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

# Author

## Aadhya

- GitHub: https://github.com/aadhyadpatel47
- LinkedIn: https://www.linkedin.com/in/aadhyapatel

---

# License

MIT License

Free to use, modify, and distribute.
