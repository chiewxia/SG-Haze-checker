# Haze Checker 🌫️📱

Every hour this checks the NEA haze reading for **West Singapore** (the same
data haze.gov.sg shows) and sends a push notification to your iPhone when it
goes **above 55**.

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

That's it. It now checks every hour at :15.

## Changing settings (optional)

Under **Settings → Secrets and variables → Actions → Variables**, add any of:

| Variable    | Default | Options                                              |
|-------------|---------|------------------------------------------------------|
| `REGION`    | `west`  | `west`, `east`, `central`, `north`, `south`          |
| `THRESHOLD` | `55`    | any number; alerts when the reading is **above** it  |
| `METRIC`    | `pm25`  | `pm25` = 1-hr PM2.5 (µg/m³), `psi` = 24-hr PSI       |

**Which number is "55"?** haze.gov.sg shows two numbers:

- **1-hr PM2.5** (default here). NEA's "Normal" band is 0–55 µg/m³, and
  56+ is "Elevated". So 55 is NEA's own cut-off for this one.
- **24-hr PSI.** 0–50 is "Good", 51–100 "Moderate". If you meant PSI 55, set
  `METRIC` to `psi`.

## Things to know

- **You get an alert every hour while it stays above the limit**, not just once.
- GitHub sometimes runs scheduled jobs 5–20 minutes late at busy times.
- GitHub pauses scheduled jobs if the repo has no activity for 60 days. If
  that happens, you'll get an email; click **Enable workflow** in the Actions tab.
- Tapping the notification opens haze.gov.sg.

## Run locally

```bash
NTFY_TOPIC=your-topic FORCE_TEST=1 python3 haze_check.py
python3 -m unittest
```
