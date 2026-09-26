"""
Simulates one bus driving a route and generates FleetSight events.

This is the "edge" side of the demo. In production this runs on the bus
with a real camera + YOLOv8 + GPS module. For the hackathon prototype it:
  1. Fakes a GPS trail (linear interpolation between waypoints)
  2. Fakes detections at given points along the trail
  3. POSTs each event to the backend API

To swap in REAL detection later, replace `fake_detections_along_route()`
with actual YOLOv8 inference per video frame (see detect_real.py stub).

Usage:
    pip install requests
    python3 simulate_bus.py
"""

import time
import requests
from datetime import datetime, timedelta, timezone

API_URL = "http://localhost:8000/events"

# A short fake route: (lat, lon) waypoints along a road
ROUTE = [
    (13.0820, 80.2700),
    (13.0824, 80.2703),
    (13.0827, 80.2707),   # <- pothole here
    (13.0831, 80.2711),
    (13.0835, 80.2715),
]


def interpolate(p1, p2, steps=5):
    for i in range(steps):
        t = i / steps
        yield (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


def fake_detections_along_route(bus_id, start_time, pothole_at_index=2):
    """Yields (event_type, lat, lon, confidence, timestamp) tuples."""
    t = start_time
    for i, wp in enumerate(ROUTE):
        # normal vehicles seen continuously
        yield ("vehicle", wp[0], wp[1], 0.95, t)
        t += timedelta(seconds=8)

        # the pothole gets "seen" only near its waypoint
        if i == pothole_at_index:
            yield ("pothole", wp[0] + 0.00002, wp[1] - 0.00001, 0.87, t)
            t += timedelta(seconds=2)


def send_event(event_type, lat, lon, confidence, bus_id, ts):
    payload = {
        "type": event_type,
        "lat": lat, "lon": lon,
        "confidence": confidence,
        "bus_id": bus_id,
        "timestamp": ts.isoformat(),
    }
    try:
        r = requests.post(API_URL, json=payload, timeout=5)
        r.raise_for_status()
        result = r.json()
        print(f"[{bus_id}] {event_type} @ ({lat:.5f},{lon:.5f}) "
              f"-> {result['action']} (event_conf={result['event']['event_confidence']:.2f})")
    except requests.exceptions.RequestException as e:
        print(f"  ! Could not reach backend at {API_URL} — is `uvicorn api:app` running? ({e})")


if __name__ == "__main__":
    now = datetime.now(timezone.utc)

    print("=== BUS_17 driving the route ===")
    for etype, lat, lon, conf, ts in fake_detections_along_route("BUS_17", now):
        send_event(etype, lat, lon, conf, "BUS_17", ts)
        time.sleep(0.1)  # small delay so it reads like a live feed in the demo

    print("\n=== BUS_23 drives the SAME route 45 minutes later (for the fusion demo) ===")
    later = now + timedelta(minutes=45)
    for etype, lat, lon, conf, ts in fake_detections_along_route("BUS_23", later):
        if etype == "pothole":  # only send the pothole re-detection for a clean demo
            send_event(etype, lat, lon, conf - 0.03, "BUS_23", ts)
