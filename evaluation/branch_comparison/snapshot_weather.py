"""Capture one public forecast for paired weather regressions. No keys needed."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.request import urlopen

URL = "https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new snapshot filename")
    with urlopen(URL, timeout=15) as response:
        raw = response.read(100001)
    if len(raw) > 100000:
        raise ValueError("Oversized forecast")
    payload = json.loads(raw)
    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        raise ValueError("Unexpected forecast response")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump({"url": URL, "assessed_at": datetime.now(timezone.utc).isoformat(), "payload": payload}, stream, indent=2)
    print("Snapshot saved. Review its issue time and forecast dates before labelling weather cases.")
