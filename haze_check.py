#!/usr/bin/env python3
"""Check NEA haze readings for chosen regions and alert via ntfy and/or Telegram.

Data is the same feed haze.gov.sg displays (NEA via data.gov.sg).
Standard library only, so it runs anywhere Python 3.8+ exists.

Config (environment variables):
  NTFY_TOPIC   your private ntfy topic name
  TELEGRAM_BOT_TOKEN  token from @BotFather
  TELEGRAM_CHAT_ID    chat/group ID(s) to message, comma-separated
               (set NTFY_TOPIC, the Telegram pair, or both)
  REGIONS      default "west,central"  comma-separated regions to watch
                                (west/east/central/north/south); alert if ANY
                                is above the threshold
  THRESHOLD    default 55       alert when the reading is ABOVE this
  METRIC       default "pm25"   "pm25" = 1-hr PM2.5 (µg/m³), "psi" = 24-hr PSI
  NTFY_SERVER  default "https://ntfy.sh"
  FORCE_TEST   if "1", always send a notification (to check your setup)
  STOP_MINUTE  default 15       keep retrying until this minute past the hour
                                for NEA to publish this hour's reading
  POLL_SECONDS default 30       how often to retry while waiting
"""
import html
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

API_BASE = "https://api-open.data.gov.sg/v2/real-time/api/"

# metric -> (API endpoint, reading key, label, unit)
METRICS = {
    "pm25": ("pm25", "pm25_one_hourly", "1-hr PM2.5", "µg/m³"),
    "psi": ("psi", "psi_twenty_four_hourly", "24-hr PSI", ""),
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "haze-checker"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


REGION_ORDER = ["north", "south", "east", "west", "central"]


def latest_reading(payload, metric_key, regions):
    """Return (timestamp, all_regions) from a data.gov.sg payload."""
    data = payload.get("data", payload)
    items = data.get("items") or []
    if not items:
        raise ValueError("API returned no readings")
    item = items[-1]
    readings = item.get("readings", {})
    missing = [r for r in regions if r not in readings.get(metric_key, {})]
    if missing:
        raise ValueError(
            f"No {metric_key}/{','.join(missing)} in API response. "
            f"Got: {json.dumps(item)[:500]}"
        )
    all_regions = {r: float(v) for r, v in readings[metric_key].items()}
    ts = item.get("timestamp") or item.get("updatedTimestamp", "")
    return ts, all_regions


def region_summary(all_regions, regions, threshold):
    """One line per region, watched ones first; ⚠️ marks any above the limit."""
    others = [r for r in REGION_ORDER if r in all_regions and r not in regions]
    others += sorted(r for r in all_regions if r not in REGION_ORDER and r not in regions)
    lines = []
    for r in list(regions) + others:
        v = all_regions[r]
        lines.append(f"{r.title()}: {v:g}{' ⚠️' if v > threshold else ''}")
    return "\n".join(lines)


def format_time(ts):
    """'2026-09-30T18:00:00+08:00' -> '6pm'."""
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return ts
    return f"{t.hour % 12 or 12}{'am' if t.hour < 12 else 'pm'}"


def is_current_hour(ts, now=None):
    """True if the reading's timestamp is in the current clock hour."""
    try:
        reading_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    now = now or datetime.now(timezone.utc)
    # Singapore is a whole-hour offset from UTC, so flooring UTC works.
    return reading_time >= now.replace(minute=0, second=0, microsecond=0)


def fetch_fresh(url, metric_key, regions, stop_minute, poll_seconds):
    """Fetch the reading, retrying until this hour's value is published.

    Gives up at `stop_minute` past the hour and returns the latest reading.
    Returns as soon as the fresh reading appears, so the job (and the Actions
    minutes it bills) only runs as long as NEA takes to publish.
    """
    now = datetime.now(timezone.utc)
    deadline = now.replace(minute=0, second=0, microsecond=0).timestamp() + stop_minute * 60
    while True:
        ts, all_regions = latest_reading(fetch(url), metric_key, regions)
        if is_current_hour(ts) or time.time() + poll_seconds > deadline:
            if not is_current_hour(ts):
                print(f"This hour's reading isn't out yet; using latest ({ts}).")
            return ts, all_regions
        print(f"Latest reading is {ts}; waiting for this hour's update...")
        time.sleep(poll_seconds)


def send_ntfy(server, topic, title, message, priority):
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


def telegram_text(title, message):
    return (
        f"<b>{html.escape(title)}</b>\n{html.escape(message)}\n\n"
        '<a href="https://www.haze.gov.sg">haze.gov.sg</a>'
    )


def send_telegram(token, chat_id, title, message):
    body = {
        "chat_id": chat_id,
        "text": telegram_text(title, message),
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).close()


def build_channels(env):
    """Return [(name, send(title, message, priority))] for each configured channel."""
    channels = []
    topic = env.get("NTFY_TOPIC", "").strip()
    if topic:
        server = env.get("NTFY_SERVER", "https://ntfy.sh")
        channels.append(
            ("ntfy", lambda t, m, p: send_ntfy(server, topic, t, m, p))
        )
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = [c.strip() for c in env.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    if token and chat_ids:
        for chat_id in chat_ids:
            channels.append(
                (f"telegram:{chat_id}",
                 lambda t, m, p, c=chat_id: send_telegram(token, c, t, m))
            )
    elif token or chat_ids:
        sys.exit("Set both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID - see README.md")
    return channels


def notify(channels, title, message, priority):
    """Send to every channel; one failing doesn't stop the others."""
    failed = []
    for name, send in channels:
        try:
            send(title, message, priority)
            print(f"Sent via {name}.")
        except Exception as e:  # noqa: BLE001 - report and carry on
            print(f"Failed to send via {name}: {e}")
            failed.append(name)
    if failed:
        sys.exit(f"Notification failed for: {', '.join(failed)}")


def main():
    channels = build_channels(os.environ)
    if not channels:
        sys.exit("No notification channel set (NTFY_TOPIC or Telegram) - see README.md")
    regions = [
        r.strip().lower()
        for r in os.environ.get("REGIONS", "west,central").split(",")
        if r.strip()
    ]
    threshold = float(os.environ.get("THRESHOLD", "55"))
    metric = os.environ.get("METRIC", "pm25").strip().lower()
    force = os.environ.get("FORCE_TEST") == "1"
    stop_minute = int(os.environ.get("STOP_MINUTE", "15"))
    poll_seconds = float(os.environ.get("POLL_SECONDS", "30"))

    if metric not in METRICS:
        sys.exit(f"METRIC must be one of {list(METRICS)}")
    endpoint, key, label, unit = METRICS[metric]

    ts, all_regions = fetch_fresh(
        API_BASE + endpoint, key, regions, stop_minute, poll_seconds
    )
    when = format_time(ts)
    details = f"{label} at {when}{(' (' + unit + ')') if unit else ''}:\n" + region_summary(
        all_regions, regions, threshold
    )
    print(f"Watching {', '.join(regions)} above {threshold:g} ({ts})")
    print(details)

    high = [r for r in regions if all_regions[r] > threshold]
    if high:
        levels = ", ".join(f"{r.title()} {all_regions[r]:g}" for r in high)
        verb = "is" if len(high) == 1 else "are"
        notify(
            channels,
            title=f"Haze alert: {levels}",
            message=f"{' & '.join(r.title() for r in high)} {verb} above your limit of {threshold:g}.\n\n{details}",
            priority="high",
        )
        print("Alert sent.")
    elif force:
        notify(
            channels,
            title="Haze checker test",
            message=f"Setup works. Alerts fire when {' or '.join(r.title() for r in regions)} is above {threshold:g}.\n\n{details}",
            priority="default",
        )
        print("Test notification sent.")


if __name__ == "__main__":
    main()
