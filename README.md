# FleetSight Prototype

A runnable starter for the SIH26124 prototype. The fusion/persistence
engine (`backend/fusion.py`) has already been tested and works with zero
external dependencies. Everything else needs one `pip install` once you
have internet.

## What's here

```
fleetsight/
├── backend/
│   ├── fusion.py       # core engine: storage, multi-bus fusion, persistence — TESTED, no deps
│   └── api.py           # FastAPI wrapper around fusion.py — needs: pip install fastapi uvicorn
├── edge/
│   ├── simulate_bus.py  # fakes 2 buses driving a route, posts events to the API — needs: pip install requests
│   └── detect_real.py   # REAL YOLOv8 + OCR pipeline, reference implementation for later
├── dashboard/
│   └── index.html       # Leaflet map + event list, single file, just open in a browser
└── data/
    └── seed_history.py  # backdates a few days of events so "persistent defect" shows immediately
```

## Quick start (once you have internet)

```bash
# 1. Install backend deps
cd backend
pip install fastapi uvicorn

# 2. Start the API
uvicorn api:app --reload --port 8000
# leave this running in its own terminal

# 3. In a new terminal, seed some history so the demo has data immediately
cd ..
python3 data/seed_history.py

# 4. Simulate two buses driving the live demo route
pip install requests
cd edge
python3 simulate_bus.py

# 5. Open dashboard/index.html directly in your browser
# (double-click it, or `open dashboard/index.html` / `start dashboard/index.html`)
```

You should see:
- Markers appear on the map as `simulate_bus.py` runs
- The pothole from BUS_17 and BUS_23 merge into **one** marker with rising confidence (open its popup)
- The seeded history location already shows `PERSISTENT` after 4 backdated visits
- Clicking "Mark Resolved" on any event updates its status and removes it from future fusion matching

## What's real vs simulated right now

| Piece | Status |
|---|---|
| Multi-bus fusion logic | **Real** — tested in `fusion.py`, works correctly (see demo output when you run it directly) |
| Persistent memory / recurrence flagging | **Real** — same, tested |
| Repair-status feedback loop | **Real** — `PATCH /events/{id}/status`, wired into the dashboard button |
| GPS | **Simulated** — `simulate_bus.py` fakes a route; `detect_real.py` shows how to swap in real GPS reads |
| Pothole/vehicle detection | **Simulated** in `simulate_bus.py` for the demo; `detect_real.py` is the real YOLOv8 pipeline reference, ready to run once you have a trained model + GPU/internet |
| ANPR | Not yet stubbed — see note below |
| Edge hardware | Simulated — everything currently runs on a laptop; production target is a Jetson-class device on the bus |

## Next steps to fill in

1. **Get a pothole dataset** (link is in your FleetSight context doc — Roboflow Universe) and fine-tune YOLOv8:
   ```bash
   pip install ultralytics
   yolo train data=pothole.yaml model=yolov8n.pt epochs=50
   ```
   Then point `detect_real.py`'s `POTHOLE_MODEL_PATH` at the trained weights.

2. **Add ANPR** — crop vehicle bounding boxes from `detect_real.py`'s vehicle detections, run PaddleOCR/EasyOCR on the crop, send an `incident` event type with the plate string in a new field.

3. **Swap SQLite for PostgreSQL+PostGIS** once you want real geospatial indexing instead of Python-side haversine distance — `fusion.py`'s `get_db()` and the distance check in `ingest_event()` are the only two places that need to change.

4. **Record real dashcam-style footage** (even a phone recording from a car window works for the demo) instead of the fully-simulated detections, and run it through `detect_real.py`.

5. **Congestion heatmap on the dashboard** — Leaflet has a `leaflet.heat` plugin; feed it all `vehicle_density` event coordinates.
