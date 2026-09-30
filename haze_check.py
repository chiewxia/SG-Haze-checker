#!/usr/bin/env python3
"""Check NEA haze readings for one region and push an iPhone alert via ntfy.

Data is the same feed haze.gov.sg displays (NEA via data.gov.sg).
Standard library only, so it runs anywhere Python 3.8+ exists.

Config (environment variables):
  NTFY_TOPIC   required  your private ntfy topic name
  REGION       default "west"   one of west/east/central/north/south
  THRESHOLD    default 55       alert when the reading is ABOVE this
  METRIC       default "pm25"   "pm25" = 1-hr PM2.5 (µg/m³), "psi" = 24-hr PSI
  NTFY_SERVER  default "https://ntfy.sh"
  FORCE_TEST   if "1", always send a notification (to check your setup)
  MAX_WAIT     default 150      seconds to keep retrying until NEA publishes
                                this hour's reading
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

API_URL = "https://api-open.data.gov.sg/v2/real-time/api/psi"

METRICS = {
    "pm25": ("pm25_one_hourly", "1-hr PM2.5", "µg/m³"),
    "psi": ("psi_twenty_four_hourly", "24-hr PSI", ""),
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "haze-checker"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def latest_reading(payload, metric_key, region):
    """Return (value, timestamp) for the region from a data.gov.sg PSI payload."""
    data = payload.get("data", payload)
    items = data.get("items") or []
    if not items:
        raise ValueError("API returned no readings")
    item = items[-1]
    value = item["readings"][metric_key][region]
    return float(value), item.get("timestamp") or item.get("updatedTimestamp", "")


def is_current_hour(ts, now=None):
    """True if the reading's timestamp is in the current clock hour."""
    try:
        reading_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    now = now or datetime.now(timezone.utc)
    # Singapore is a whole-hour offset from UTC, so flooring UTC works.
    return reading_time >= now.replace(minute=0, second=0, microsecond=0)


def fetch_fresh(metric_key, region, max_wait, retry_every=60):
    """Fetch the reading, retrying until this hour's value is published."""
    deadline = time.monotonic() + max_wait
    while True:
        value, ts = latest_reading(fetch(API_URL), metric_key, region)
        if is_current_hour(ts) or time.monotonic() + retry_every > deadline:
            if not is_current_hour(ts):
                print(f"This hour's reading isn't out yet; using latest ({ts}).")
            return value, ts
        print(f"Latest reading is {ts}; waiting for this hour's update...")
        time.sleep(retry_every)


def notify(server, topic, title, message, priority):
    req = urllib.request.Request(
        f"{server.rstrip('/')}/{topic}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": priority,
            "Tags": "mask",
            "Click": "https://www.haze.gov.sg",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).close()


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        sys.exit("NTFY_TOPIC is not set - see README.md")
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
    region = os.environ.get("REGION", "west").strip().lower()
    threshold = float(os.environ.get("THRESHOLD", "55"))
    metric = os.environ.get("METRIC", "pm25").strip().lower()
    force = os.environ.get("FORCE_TEST") == "1"
    max_wait = float(os.environ.get("MAX_WAIT", "150"))

    if metric not in METRICS:
        sys.exit(f"METRIC must be one of {list(METRICS)}")
    key, label, unit = METRICS[metric]

    value, ts = fetch_fresh(key, region, max_wait)
    reading = f"{value:g}{(' ' + unit) if unit else ''}"
    print(f"{region.title()} {label}: {reading} at {ts} (threshold {threshold:g})")

    if value > threshold:
        notify(
            server, topic,
            title=f"Haze alert: {region.title()} {label} {value:g}",
            message=f"{region.title()} {label} is {reading}, above your limit of {threshold:g}. ({ts})",
            priority="high",
        )
        print("Alert sent.")
    elif force:
        notify(
            server, topic,
            title="Haze checker test",
            message=f"Setup works. {region.title()} {label} is {reading} (limit {threshold:g}).",
            priority="default",
        )
        print("Test notification sent.")


if __name__ == "__main__":
    main()
