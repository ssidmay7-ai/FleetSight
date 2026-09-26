"""
FleetSight core engine: event storage, multi-bus fusion, and persistent
memory. Pure Python + sqlite3 stdlib — no external dependencies, so you
can run and test this on its own before wiring up FastAPI.

Run this file directly to see a demo: python3 fusion.py
"""

import sqlite3
import math
import uuid
from datetime import datetime, timedelta, timezone

DB_PATH = "fleetsight.db"

# How close (meters) and how recent (minutes) two detections need to be
# to be considered the *same* physical event.
FUSION_RADIUS_M = 25
FUSION_WINDOW_MIN = 60 * 24 * 3  # 3 days — buses don't pass the same spot every minute

# How many independent observations before a repeat-offender location
# gets flagged as a "persistent" issue.
PERSISTENCE_THRESHOLD = 3


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            model_confidence REAL NOT NULL,
            event_confidence REAL NOT NULL,
            bus_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            observation_count INTEGER DEFAULT 1,
            first_observed TEXT NOT NULL,
            last_observed TEXT NOT NULL,
            status TEXT DEFAULT 'active',       -- active | acknowledged | resolved
            persistent INTEGER DEFAULT 0,
            resolved_at TEXT
        )
        """
    )
    return conn


def haversine_m(lat1, lon1, lat2, lon2):
    """Distance between two lat/lon points in meters."""
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def ingest_event(detection: dict):
    """
    detection = {
        "type": "pothole",
        "lat": 13.0827, "lon": 80.2707,
        "confidence": 0.89,
        "bus_id": "BUS_17",
        "timestamp": "2026-09-24T10:31:22Z"   # ISO 8601
    }

    Returns the stored event row (as dict), fused or newly created.
    This is where Innovation #2 (multi-bus fusion) and Innovation #1
    (two-tier confidence) actually happen.
    """
    conn = get_db()
    now = detection["timestamp"]
    now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))

    # Only fuse against events of the SAME type, resolved events excluded
    # (a resolved pothole that reappears is a fresh event, not a continuation).
    candidates = conn.execute(
        "SELECT * FROM events WHERE type = ? AND status != 'resolved'",
        (detection["type"],),
    ).fetchall()

    match = None
    for c in candidates:
        dist = haversine_m(detection["lat"], detection["lon"], c["lat"], c["lon"])
        last_dt = datetime.fromisoformat(c["last_observed"].replace("Z", "+00:00"))
        minutes_apart = abs((now_dt - last_dt).total_seconds()) / 60
        if dist <= FUSION_RADIUS_M and minutes_apart <= FUSION_WINDOW_MIN:
            match = c
            break

    if match:
        new_count = match["observation_count"] + 1
        # Event confidence rises with corroboration — simple, explainable
        # formula: each extra independent observation closes the gap to 1.0.
        new_event_conf = 1 - (1 - match["event_confidence"]) * (1 - detection["confidence"]) * 0.5
        new_event_conf = min(new_event_conf, 0.99)
        is_persistent = 1 if new_count >= PERSISTENCE_THRESHOLD else match["persistent"]

        conn.execute(
            """
            UPDATE events
            SET observation_count = ?, event_confidence = ?, last_observed = ?,
                persistent = ?, model_confidence = ?
            WHERE id = ?
            """,
            (new_count, new_event_conf, now, is_persistent, detection["confidence"], match["id"]),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM events WHERE id = ?", (match["id"],)).fetchone()
        conn.close()
        return dict(row), "fused"

    # No match -> brand new event
    event_id = str(uuid.uuid4())[:8]
    conn.execute(
        """
        INSERT INTO events (id, type, lat, lon, model_confidence, event_confidence,
                             bus_id, timestamp, observation_count, first_observed,
                             last_observed, status, persistent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'active', 0)
        """,
        (
            event_id, detection["type"], detection["lat"], detection["lon"],
            detection["confidence"], detection["confidence"], detection["bus_id"],
            now, now, now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    return dict(row), "created"


def set_status(event_id: str, status: str):
    """Repair-status feedback loop: authority marks an event acknowledged/resolved."""
    assert status in ("active", "acknowledged", "resolved")
    conn = get_db()
    resolved_at = datetime.now(timezone.utc).isoformat() if status == "resolved" else None
    conn.execute(
        "UPDATE events SET status = ?, resolved_at = ? WHERE id = ?",
        (status, resolved_at, event_id),
    )
    conn.commit()
    conn.close()


def list_events(status=None, only_persistent=False):
    conn = get_db()
    q = "SELECT * FROM events"
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if only_persistent:
        clauses.append("persistent = 1")
    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import os
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    print("=== Demo: Bus #17 detects a pothole ===")
    base_time = datetime(2026, 9, 24, 10, 31, 22, tzinfo=timezone.utc)
    e1, action = ingest_event({
        "type": "pothole", "lat": 13.0827, "lon": 80.2707,
        "confidence": 0.89, "bus_id": "BUS_17",
        "timestamp": base_time.isoformat(),
    })
    print(f"  -> {action}, event_confidence={e1['event_confidence']:.2f}, observations={e1['observation_count']}")

    print("\n=== Bus #23 passes the same spot 40 minutes later ===")
    e2, action = ingest_event({
        "type": "pothole", "lat": 13.08272, "lon": 80.27068,  # ~2m away
        "confidence": 0.84, "bus_id": "BUS_23",
        "timestamp": (base_time + timedelta(minutes=40)).isoformat(),
    })
    print(f"  -> {action}, event_confidence={e2['event_confidence']:.2f}, observations={e2['observation_count']}")

    print("\n=== A third bus confirms it the next day ===")
    e3, action = ingest_event({
        "type": "pothole", "lat": 13.08269, "lon": 80.27071,
        "confidence": 0.91, "bus_id": "BUS_05",
        "timestamp": (base_time + timedelta(days=1)).isoformat(),
    })
    print(f"  -> {action}, event_confidence={e3['event_confidence']:.2f}, "
          f"observations={e3['observation_count']}, persistent={bool(e3['persistent'])}")

    print("\n=== Authority marks it resolved ===")
    set_status(e3["id"], "resolved")
    print("  -> status set to resolved")

    print("\n=== Same location reported again after repair (should be a NEW event) ===")
    e4, action = ingest_event({
        "type": "pothole", "lat": 13.08270, "lon": 80.27069,
        "confidence": 0.77, "bus_id": "BUS_11",
        "timestamp": (base_time + timedelta(days=5)).isoformat(),
    })
    print(f"  -> {action} (id={e4['id']}) — confirms resolved events don't get merged into")

    print("\n=== All events currently in DB ===")
    for ev in list_events():
        print(f"  {ev['id']} | {ev['type']:8s} | conf={ev['event_confidence']:.2f} | "
              f"obs={ev['observation_count']} | persistent={bool(ev['persistent'])} | status={ev['status']}")
