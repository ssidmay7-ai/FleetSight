"""
FleetSight backend API.

Setup (once you have internet):
    pip install fastapi uvicorn

Run:
    uvicorn api:app --reload --port 8000

Then open dashboard/index.html in a browser (it points at localhost:8000).
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import fusion

app = FastAPI(title="FleetSight API")

# Allow the dashboard (opened as a local file / different port) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Detection(BaseModel):
    type: str          # "pothole" | "vehicle" | "pedestrian_risk" | "incident"
    lat: float
    lon: float
    confidence: float
    bus_id: str
    timestamp: str      # ISO 8601, e.g. 2026-09-24T10:31:22Z


class StatusUpdate(BaseModel):
    status: str          # "active" | "acknowledged" | "resolved"


@app.post("/events")
def create_event(detection: Detection):
    row, action = fusion.ingest_event(detection.model_dump())
    return {"action": action, "event": row}


@app.get("/events")
def get_events(status: str | None = None, persistent_only: bool = False):
    return fusion.list_events(status=status, only_persistent=persistent_only)


@app.patch("/events/{event_id}/status")
def update_status(event_id: str, body: StatusUpdate):
    events = fusion.list_events()
    if not any(e["id"] == event_id for e in events):
        raise HTTPException(status_code=404, detail="Event not found")
    fusion.set_status(event_id, body.status)
    return {"id": event_id, "status": body.status}


@app.get("/health")
def health():
    return {"status": "ok"}
