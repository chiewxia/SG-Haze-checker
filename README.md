# SG Haze Checker – West & Central 🌫️📱

Hourly haze alerts for Singapore. Every hour this checks NEA's 1-hr PM2.5
readings (the same data haze.gov.sg shows) and sends an alert when **West or
Central** goes **above 55**, NEA's cut-off for the "Normal" band.

## Get alerts on Telegram

**Add [@sg_haze_checker_bot](https://t.me/sg_haze_checker_bot) to your group.**
That's it. The group is subscribed automatically.

- **Just for yourself?** Open [@sg_haze_checker_bot](https://t.me/sg_haze_checker_bot)
  and tap **Start**.
- **To stop:** send `/stop`, or remove the bot from the group.
- **To resubscribe:** send `/start` (in a group: `/start@sg_haze_checker_bot`).

The bot checks in once an hour, so the welcome message (and any reply to
`/start` or `/stop`) can take up to an hour to arrive.

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

haze.gov.sg
```

West and Central are listed first. ⚠️ marks any region above 55, but only
West and Central trigger an alert. While the air stays above 55, you get an
update every hour. Nothing is sent when the air is fine.

## Privacy

- Nobody else can see who uses the bot. The group list is stored encrypted,
  and names or group titles never appear in this repo or its logs.
- The bot only reacts to `/start` and `/stop`. It ignores other messages in
  your group.

---

## For the maintainer

Runs free on GitHub Actions (public repo = unlimited minutes). Your phone
doesn't need to be on.

### Secrets

Settings → Secrets and variables → Actions → **Secrets** tab (never
"Variables", which are public):

| Secret | What it's for |
|---|---|
| `TELEGRAM_BOT_TOKEN` | the bot's token |
| `TELEGRAM_OWNER_CHAT_ID` | your chat: gets "who added the bot where" reports (➕ ➖ 🔔 🔕 ⛔) and test messages |
| `TELEGRAM_CHAT_ID` | optional: chats that should *always* get alerts, comma-separated |
| `NTFY_TOPIC` | optional: also push to your private [ntfy](https://apps.apple.com/app/ntfy/id1625396347) topic. Don't share the topic name; anyone with it can read and post to it |

**Test:** Actions → Hourly haze check → **Run workflow**. Tests go only to
you (owner, `TELEGRAM_CHAT_ID`, ntfy), never to subscribers' groups. On a
phone, open the repo in Safari → **aA → Request Desktop Website** to see the
button.

### Settings (optional)

Settings → Secrets and variables → Actions → **Variables** tab:

| Variable | Default | Options |
|---|---|---|
| `REGIONS` | `west,central` | comma-separated; any of `west`, `east`, `central`, `north`, `south`. Alerts if **any** is above the threshold |
| `THRESHOLD` | `55` | alerts when a reading is **above** it |
| `METRIC` | `pm25` | `pm25` = 1-hr PM2.5 (µg/m³), `psi` = 24-hr PSI (not yet tested live; run a test after switching) |
| `TELEGRAM_MAX_CHATS` | `50` | new groups beyond this are turned away (you get a ⛔ report) |

### How it works

- **Timing:** NEA stamps each reading on the hour and publishes it a few
  minutes later. The check starts at **:05** and retries every 30 s until
  **:15**, stopping as soon as the new reading appears (otherwise it uses the
  latest available). GitHub sometimes starts scheduled runs 5–20 min late.
- **Subscribers:** each run reads new bot activity (joins, removals, `/start`,
  `/stop`) and updates the group list. Chats that remove or block the bot are
  dropped automatically.
- **Storage:** the list (chat IDs only) is kept in the Actions cache,
  AES-256 encrypted with the bot token. If the cache is ever cleared, or you
  change the token, groups need to `/start@sg_haze_checker_bot` again.
  `TELEGRAM_CHAT_ID` chats are never lost.
- If the workflow is paused for over 24 hours, Telegram discards joins and
  `/start`s from that time; those chats need to `/start` again.

### Privacy & cost

- Token and chat IDs live only in GitHub secrets: encrypted, masked as `***`
  in logs, and not given to forks or pull requests. Only people with write
  access can run the workflow.
- Who used the bot is sent only to you in Telegram. Logs show counts only.
- **Free, and abuse can't cost money.** The Telegram Bot API has no billing
  (over its rate limits it just rejects messages), and public repos get
  unlimited Actions minutes. The worst case is someone adding the bot to
  groups (capped, and you're told). If the token leaks: @BotFather →
  `/revoke`, then update the secret.

### Upkeep

- GitHub pauses scheduled jobs after 60 days with no repo activity. You'll get
  an email; click **Enable workflow** in the Actions tab.
- **To stop everything:** Actions → Hourly haze check → **⋯ → Disable workflow**.

### Run locally

```bash
NTFY_TOPIC=your-topic FORCE_TEST=1 python3 haze_check.py
python3 -m unittest
```
