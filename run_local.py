"""
Local development runner for Insight Flow.

Vercel deploys api/index.py. Use this file only for local manual runs:
python run_local.py
"""

import os

import uvicorn


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    uvicorn.run("insightflow_app:app", host=host, port=port, reload=False)
