"""
Seeds a few days of backdated events so the "persistent defect" and
"recurring congestion" parts of the demo have history to show immediately,
instead of needing to wait real days.

Run this AFTER starting the backend once (so fleetsight.db exists), or run
it standalone — it talks to fusion.py directly, not through the API.

Usage:
    cd backend
    python3 ../data/seed_history.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from datetime import datetime, timedelta, timezone
import fusion

BASE_LAT, BASE_LON = 13.0900, 80.2600  # a second, separate location from the live demo route
now = datetime.now(timezone.utc)

print("Seeding a recurring pothole over 4 days (for the persistence demo)...")
buses = ["BUS_02", "BUS_09", "BUS_14", "BUS_21"]
for i, bus in enumerate(buses):
    ts = now - timedelta(days=4 - i, hours=2)
    row, action = fusion.ingest_event({
        "type": "pothole",
        "lat": BASE_LAT + 0.00001 * i,
        "lon": BASE_LON - 0.00001 * i,
        "confidence": 0.80 + i * 0.02,
        "bus_id": bus,
        "timestamp": ts.isoformat(),
    })
    print(f"  Day -{4-i}: {bus} -> {action}, observations={row['observation_count']}, "
          f"persistent={bool(row['persistent'])}")

print("\nSeeding recurring morning congestion at a junction (5 weekdays)...")
JUNCTION_LAT, JUNCTION_LON = 13.0950, 80.2650
for d in range(5):
    ts = now - timedelta(days=5 - d)
    ts = ts.replace(hour=8, minute=30)
    row, action = fusion.ingest_event({
        "type": "vehicle_density",
        "lat": JUNCTION_LAT, "lon": JUNCTION_LON,
        "confidence": 0.9,
        "bus_id": f"BUS_{d+1:02d}",
        "timestamp": ts.isoformat(),
    })
    print(f"  Weekday -{5-d} 08:30: -> {action}, observations={row['observation_count']}")

print("\nDone. Start the API and dashboard to see this history on the map.")
