"""
Local development runner for Insight Flow.

The deployable Vercel entrypoint is api/index.py. Keeping this file from
exposing a top-level variable named `app` avoids Vercel detecting a second
FastAPI function.
"""

import os

import uvicorn


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    uvicorn.run("insightflow_app:app", host=host, port=port, reload=False)
