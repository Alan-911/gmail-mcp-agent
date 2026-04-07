"""FastAPI dashboard server — serves classification log as JSON for the React frontend."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import json
import os
from pathlib import Path

app = FastAPI(title="Gmail MCP Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_PATH = Path("classification_log.json")


@app.get("/api/log")
def get_log(limit: int = 100):
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH) as f:
        data = json.load(f)
    return data[-limit:]


@app.get("/api/stats")
def get_stats():
    if not LOG_PATH.exists():
        return {}
    with open(LOG_PATH) as f:
        data = json.load(f)
    stats: dict = {}
    for entry in data:
        cat = entry.get("category", "UNKNOWN")
        stats[cat] = stats.get(cat, 0) + 1
    return {"total": len(data), "breakdown": stats}


@app.get("/")
def root():
    return {"status": "Gmail MCP Dashboard running", "endpoints": ["/api/log", "/api/stats"]}
