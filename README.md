# SG Haze Checker – West & Central 🌫️📱

Every hour this checks NEA's 1-hr PM2.5 readings (the same data haze.gov.sg
shows) and sends a push notification to your iPhone when **West or Central**
goes **above 55**.

It runs free on GitHub Actions, so your phone doesn't need to be on or have
any app open. Notifications come through the free **ntfy** app and/or a
**Telegram** bot.

## What an alert looks like

```
Haze alert: West 61, Central 58
West & Central are above your limit of 55.

1-hr PM2.5 at 7pm (µg/m³):
West: 61 ⚠️
Central: 58 ⚠️
North: 70 ⚠️
South: 11
East: 9
```

Watched regions are listed first. ⚠️ marks any region above 55, but only the
watched ones (West, Central) trigger an alert. Tapping it opens haze.gov.sg.

## Setup (about 5 minutes)

1. **Install ntfy on your iPhone.** Get
   [ntfy from the App Store](https://apps.apple.com/app/ntfy/id1625396347),
   open it, allow notifications.
2. **Pick a private topic name.** Tap **+** and subscribe to a topic name that's
   hard to guess, e.g. `haze-sg-8x2k-qz`. Anyone who knows the name can see
   its messages, so don't use something like `haze`.
3. **Tell GitHub your topic.** In this repo on GitHub, go to
   **Settings → Secrets and variables → Actions → New repository secret**.
   Name: `NTFY_TOPIC`, value: your topic name.
4. **Send a test.** Go to **Actions → Hourly haze check → Run workflow**
   (leave "Send a test notification" ticked). Your phone should buzz within a
   minute.

   On a phone, the **Run workflow** button is hidden. Open the repo in Safari
   and choose **aA → Request Desktop Website**, or use a computer.

That's it. It checks every hour on its own; nothing else to run.

## Telegram alerts (optional)

A Telegram bot sends the same alerts to **every group it's added to** and to
anyone who messages it `/start`. Works alongside ntfy or instead of it.

### Setup

1. **Create a bot.** In Telegram, message **@BotFather** → `/newbot` → pick a
   name and a username ending in `bot`. It replies with a **token** like
   `123456789:AAH...`. Keep it private.
2. **Get your own chat ID** (so the bot can report to you). Open your bot,
   tap **Start**, then open this in a browser with your token in it:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   and find `"chat":{"id": ...}`. If you see `"result":[]`, send the bot
   another message and reload.
3. **Add secrets** (Settings → Secrets and variables → Actions):

   | Secret | Value |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | the token (required) |
   | `TELEGRAM_OWNER_CHAT_ID` | your chat ID: you get "who added the bot where" reports and test messages |
   | `TELEGRAM_CHAT_ID` | optional: chats that should *always* get alerts, comma-separated |

4. **Send a test** (Actions → Hourly haze check → Run workflow). Tests go only
   to the owner and `TELEGRAM_CHAT_ID`, never to everyone's groups.

### How subscribing works

| Someone… | What happens (at the next hourly run) |
|---|---|
| adds the bot to a group | group is subscribed and gets a welcome message; you get "➕ Jane (@jane) added the bot to group "Family"" |
| sends `/start` to the bot (or `/start@YourBot` in a group) | that chat is subscribed and welcomed; you get a 🔔 report |
| sends `/stop` | that chat is unsubscribed; you get a 🔕 report |
| removes the bot from a group, or blocks it | chat is unsubscribed; you get a ➖ report |

You'll want alerts yourself too: sending the bot `/start` subscribes your own
chat.

**Things to know:**

- **Replies aren't instant.** The bot only checks messages during the hourly
  run, so welcomes and reports arrive up to an hour later.
- **Anyone who finds the bot can add it** to their group and get alerts.
  You'll be told each time. Telegram shows you who added it and where, but
  never who read a message.
- **The subscriber list is stored in GitHub's Actions cache** (chat IDs only;
  names are sent only to you in Telegram, never saved to files or logs,
  since a public repo's logs are public). If GitHub ever clears the cache,
  groups need to send `/start@YourBot` again to resubscribe; fixed
  `TELEGRAM_CHAT_ID` chats are never lost.
- If the workflow is paused for more than 24 hours, Telegram discards joins
  and `/start`s from that time; those chats need to `/start` again.
- If a send fails for reasons other than the bot being removed, ntfy still
  goes out and the run shows as failed in the Actions tab.

## Sharing with others

**Telegram (easiest for others):** add them to a group with the bot, or tell
them to message the bot `/start`. Alerts come from the bot's account, so
members can't fake them.

**ntfy:** install ntfy → tap **+** → subscribe to your topic name → allow
notifications.

- The topic name works like a shared password. Anyone with it can read the
  alerts and also post to the topic, so share it only with people you trust.
- If it leaks, pick a new topic, update the `NTFY_TOPIC` secret, and send the
  new name to the people you want to keep.
- Everyone gets the same alerts. Someone who wants different regions or a
  different threshold needs their own copy of this repo.

## Changing settings (optional)

Under **Settings → Secrets and variables → Actions → Variables**, add any of:

| Variable    | Default        | Options                                                                          |
|-------------|----------------|----------------------------------------------------------------------------------|
| `REGIONS`   | `west,central` | comma-separated; any of `west`, `east`, `central`, `north`, `south`. Alerts if **any** is above the threshold |
| `THRESHOLD` | `55`           | any number; alerts when a reading is **above** it                                 |
| `METRIC`    | `pm25`         | `pm25` = 1-hr PM2.5 (µg/m³), `psi` = 24-hr PSI (not yet tested live; run a test after switching) |

**Why 55?** NEA's 1-hr PM2.5 "Normal" band is 0–55 µg/m³, and 56+ is
"Elevated". So alerts fire as soon as air leaves NEA's Normal band.

## Timing

NEA stamps each reading on the hour (e.g. 10:00) and publishes it a few
minutes later. The check starts at **:05** and retries every 30 seconds until
**:15**, stopping the moment the new reading appears. If it's still not out by
:15, it uses the latest reading available (last hour's), so you never miss a
check.

## Things to know

- **You get an alert every hour while it stays above the limit**, not just once.
- GitHub sometimes runs scheduled jobs 5–20 minutes late at busy times.
- **Public repo:** unlimited free Actions minutes, but GitHub pauses scheduled
  jobs after 60 days with no repo activity. You'll get an email; click
  **Enable workflow** in the Actions tab.
- **Private repo:** runs use your free 2,000 Actions minutes/month. Each run is
  billed by how long it waits for NEA, rounded up to the minute (~2 min if NEA
  publishes by :06, ~3 min by :07). If NEA is regularly slow you may run out
  near month-end; GitHub just stops the runs and won't charge you.
- **To stop it:** Actions → Hourly haze check → **⋯ → Disable workflow**.

## Run locally

```bash
NTFY_TOPIC=your-topic FORCE_TEST=1 python3 haze_check.py
python3 -m unittest
```
