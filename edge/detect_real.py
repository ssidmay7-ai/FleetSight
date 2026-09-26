"""
REAL detection pipeline (replace simulate_bus.py's fake detections with this
once you have internet + a trained model). Not runnable in a sandboxed
environment without internet — this is the reference implementation to
run on your own machine.

Setup:
    pip install ultralytics opencv-python paddleocr requests

Usage:
    python3 detect_real.py --video sample_bus_footage.mp4 --bus-id BUS_17
"""

import argparse
import time
from datetime import datetime, timezone

import cv2
import requests
from ultralytics import YOLO

API_URL = "http://localhost:8000/events"

# Train this yourself on a pothole dataset (see references in FleetSight docs),
# or start with a pretrained COCO model for vehicle detection only.
POTHOLE_MODEL_PATH = "runs/detect/train-2/weights/best.pt"
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}  # COCO ids


def fake_gps_for_frame(frame_idx, total_frames, route):
    """Until you have real GPS hardware, interpolate position along a fixed
    route based on how far through the video you are. Swap this for real
    GPS reads once available."""
    t = frame_idx / max(total_frames - 1, 1)
    idx = min(int(t * (len(route) - 1)), len(route) - 2)
    local_t = (t * (len(route) - 1)) - idx
    lat = route[idx][0] + (route[idx + 1][0] - route[idx][0]) * local_t
    lon = route[idx][1] + (route[idx + 1][1] - route[idx][1]) * local_t
    return lat, lon


def send_event(event_type, lat, lon, confidence, bus_id):
    payload = {
        "type": event_type, "lat": lat, "lon": lon,
        "confidence": round(float(confidence), 3), "bus_id": bus_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        requests.post(API_URL, json=payload, timeout=3)
    except requests.exceptions.RequestException:
        pass  # in production: write to local offline buffer instead


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--bus-id", default="BUS_01")
    parser.add_argument("--route", nargs=4, type=float,
                         default=[13.0820, 80.2700, 13.0835, 80.2715],
                         help="start_lat start_lon end_lat end_lon")
    args = parser.parse_args()

    route = [(args.route[0], args.route[1]), (args.route[2], args.route[3])]

    pothole_model = YOLO(POTHOLE_MODEL_PATH)   # your fine-tuned model
    vehicle_model = YOLO("yolov8n.pt")          # pretrained, detects vehicles out of the box

    cap = cv2.VideoCapture(args.video)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_idx = 0

    # process every Nth frame — running inference on every single frame is
    # wasteful; a bus doesn't need pothole detection at 30fps
    SAMPLE_EVERY = 5

    while cap.isOpened():
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % SAMPLE_EVERY == 0:
            lat, lon = fake_gps_for_frame(frame_idx, total_frames, route)

            pothole_results = pothole_model(frame, verbose=False)[0]
            for box in pothole_results.boxes:
                conf = float(box.conf[0])
                if conf > 0.5:
                    send_event("pothole", lat, lon, conf, args.bus_id)

            vehicle_results = vehicle_model(frame, verbose=False)[0]
            vehicle_count = sum(
                1 for box in vehicle_results.boxes if int(box.cls[0]) in VEHICLE_CLASSES
            )
            if vehicle_count > 0:
                send_event("vehicle_density", lat, lon, 0.95, args.bus_id)

        frame_idx += 1

    cap.release()
    print(f"Processed {frame_idx} frames from {args.video}")


if __name__ == "__main__":
    main()
