# SG Haze Checker – West 🌫️📱

Every hour this checks NEA's 1-hr PM2.5 readings (the same data haze.gov.sg
shows) and sends a push notification to your iPhone when **West or Central**
goes **above 55**. Each alert lists all five regions, with ⚠️ on any above 55.

It runs free on GitHub Actions, so your phone doesn't need to be on or have
any app open. Notifications come through the free **ntfy** app.

## Setup (about 5 minutes)

1. **Install ntfy on your iPhone.** Get
   [ntfy from the App Store](https://apps.apple.com/app/ntfy/id1625396347),
   open it, allow notifications.
2. **Pick a private topic name.** Tap **+** and subscribe to a topic name that's
   hard to guess, e.g. `haze-west-8x2k-qz`. Anyone who knows the name can
   see its messages, so don't use something like `haze`.
3. **Tell GitHub your topic.** In this repo on GitHub, go to
   **Settings → Secrets and variables → Actions → New repository secret**.
   Name: `NTFY_TOPIC`, value: your topic name.
4. **Send a test.** Go to **Actions → Hourly haze check → Run workflow**
   (leave "Send a test notification" ticked). Your phone should buzz within a
   minute.

That's it. It now checks every hour, timed to NEA's hourly update (see below).

## Changing settings (optional)

Under **Settings → Secrets and variables → Actions → Variables**, add any of:

| Variable    | Default | Options                                              |
|-------------|---------|------------------------------------------------------|
| `REGIONS`   | `west,central` | comma-separated; any of `west`, `east`, `central`, `north`, `south`. Alerts if **any** is above the threshold |
| `THRESHOLD` | `55`    | any number; alerts when the reading is **above** it  |
| `METRIC`    | `pm25`  | `pm25` = 1-hr PM2.5 (µg/m³), `psi` = 24-hr PSI       |

**Which number is "55"?** haze.gov.sg shows two numbers:

- **1-hr PM2.5** (default here). NEA's "Normal" band is 0–55 µg/m³, and
  56+ is "Elevated". So 55 is NEA's own cut-off for this one.
- **24-hr PSI.** 0–50 is "Good", 51–100 "Moderate". If you meant PSI 55, set
  `METRIC` to `psi`.

## Timing

NEA stamps each reading on the hour (e.g. 10:00) and publishes it a few
minutes later. The check starts at **:05** and retries every 30 seconds until
**:15**, stopping the moment the new reading appears. If it's still not out by
:15, it uses the latest reading available (last hour's), so you never miss a
check.

## Things to know

- **You get an alert every hour while it stays above the limit**, not just once.
- GitHub sometimes runs scheduled jobs 5–20 minutes late at busy times.
- **Actions minutes (private repos only).** Each run is billed by how long it
  waits for NEA, rounded up to the minute: ~2 min if NEA publishes by :06,
  ~3 min by :07. The free plan's 2,000 min/month covers about 2.7 min per
  hourly run, so if NEA is regularly later than ~:06, you'll run out near the
  end of the month (GitHub just stops the runs; it won't charge you). Making
  the repo **public** removes the limit entirely; your ntfy topic stays
  hidden because it's a secret.
- Tapping the notification opens haze.gov.sg.

## Run locally

```bash
NTFY_TOPIC=your-topic FORCE_TEST=1 python3 haze_check.py
python3 -m unittest
```
