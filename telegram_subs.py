"""Telegram subscribers: every group the bot is in, plus people who sent /start.

Telegram only keeps a bot's incoming updates for 24 hours, and this runs
hourly, so each run pulls new updates (getUpdates), updates the subscriber
list, and saves it to a small JSON file that the workflow keeps in the Actions
cache between runs.

Only chat IDs are stored. Names (who added the bot where) are sent to the
owner as Telegram messages, never written to files or logs, since a public
repo's logs are public.
"""
import html
import json
import os
import urllib.error
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    def __init__(self, code, description, migrate_to=None):
        super().__init__(f"Telegram error {code}: {description}")
        self.code = code
        self.description = description or ""
        self.migrate_to = migrate_to

    @property
    def chat_gone(self):
        """Bot was removed/blocked, or the chat no longer exists."""
        return self.code == 403 or (
            self.code == 400 and "chat not found" in self.description.lower()
        )


def call(token, method, **params):
    req = urllib.request.Request(
        API.format(token=token, method=method),
        data=json.dumps(params).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
        except ValueError:
            raise TelegramError(e.code, e.reason) from None
    if not body.get("ok"):
        raise TelegramError(
            body.get("error_code"),
            body.get("description"),
            (body.get("parameters") or {}).get("migrate_to_chat_id"),
        )
    return body["result"]


def send_message(token, chat_id, text):
    call(
        token, "sendMessage",
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        link_preview_options={"is_disabled": True},
    )


# --- subscriber list -------------------------------------------------------

def load_state(path):
    try:
        with open(path) as f:
            state = json.load(f)
    except (FileNotFoundError, ValueError):
        state = {}
    state.setdefault("offset", 0)
    state.setdefault("chats", {})
    return state


def save_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)


def _command(text):
    """'/regions@HazeBot west, east' -> ('/regions', 'west, east')."""
    parts = (text or "").split(maxsplit=1)
    if not parts or not parts[0].startswith("/"):
        return "", ""
    return parts[0].split("@")[0].lower(), (parts[1] if len(parts) > 1 else "")


SETTINGS_COMMANDS = ("/regions", "/addregion", "/removeregion", "/threshold", "/settings", "/help")
CHANGE_COMMANDS = ("/regions", "/addregion", "/removeregion", "/threshold")
ALL_REGIONS = ["north", "south", "east", "west", "central"]
# Shown by Telegram itself, instantly, even though the bot only reads
# messages at each hourly check. Edit these to change what people see.
BOT_COMMANDS = [
    ("settings", "Show this chat's settings (reply at next hourly check)"),
    ("regions", "Set regions, e.g. /regions west central (applies next check)"),
    ("addregion", "Add regions, e.g. /addregion north (applies next check)"),
    ("removeregion", "Remove regions, e.g. /removeregion west (applies next check)"),
    ("threshold", "Set alert level, e.g. /threshold 60 (applies next check)"),
    ("stop", "Stop haze alerts in this chat (applies next check)"),
    ("start", "Start haze alerts in this chat (applies next check)"),
    ("help", "How this bot works (reply at next hourly check)"),
]
BOT_SHORT_DESCRIPTION = (  # profile / share card, max 120 chars
    "Hourly Singapore haze (PM2.5) alerts. Commands are processed at the "
    "next hourly check."
)
BOT_DESCRIPTION = (  # shown in an empty chat before Start, max 512 chars
    "🌫️ Hourly haze alerts for Singapore, using NEA's 1-hr PM2.5 readings.\n\n"
    "Add me to a group, or tap Start, to get alerts when West or Central goes "
    "above 40. Change this per chat with /regions, /addregion, /removeregion "
    "and /threshold.\n\n"
    "⏱ I check in once an hour, so replies and changes take effect at the "
    "next hourly check (up to an hour)."
)
COMMANDS_VERSION = 4


# --- per-chat settings -----------------------------------------------------

def parse_regions(args):
    """'west, Central' -> ['west', 'central']; 'all' -> every region.

    Returns (regions, None) or (None, error message).
    """
    words = [w for w in args.replace(",", " ").lower().split() if w]
    if not words:
        return None, "Tell me which regions, e.g. /regions west central"
    if words == ["all"]:
        return list(ALL_REGIONS), None
    bad = [w for w in words if w not in ALL_REGIONS]
    if bad:
        return None, f"Unknown region: {', '.join(bad)}"
    return list(dict.fromkeys(words)), None


def parse_threshold(args):
    """'60' -> 60.0. Returns (value, None) or (None, error message)."""
    try:
        value = float(args.strip())
    except ValueError:
        return None, "Give a number, e.g. /threshold 60"
    if not 1 <= value <= 500:
        return None, "Pick a number between 1 and 500"
    return value, None


def chat_settings(state, chat_id, defaults):
    """(regions, threshold) for a chat, falling back to the defaults."""
    chat = state["chats"].get(str(chat_id), {})
    return (
        chat.get("regions", defaults["regions"]),
        chat.get("threshold", defaults["threshold"]),
    )


def describe_settings(regions, threshold, label):
    return (
        f"alerts when {' or '.join(r.title() for r in regions)} {label} "
        f"goes above {threshold:g}"
    )


def help_text(defaults):
    label = defaults["label"]
    return (
        "🌫️ <b>SG Haze Checker</b>\n"
        f"Checks NEA's {label} every hour and alerts this chat when your "
        "chosen regions go above your limit.\n\n"
        "/settings – show this chat's settings\n"
        "/regions west central – set regions (north, south, east, west, "
        "central, or all)\n"
        "/addregion north – add regions · /removeregion west – remove\n"
        f"/threshold 60 – alert level (default {defaults['threshold']:g}; NEA's Normal band is 0–55)\n"
        "/stop – stop alerts · /start – resume\n\n"
        "Settings only affect this chat. In groups, only admins can change "
        "them. Replies can take up to an hour, as the bot checks in hourly."
    )


def apply_command(state, chat_id, cmd, args, defaults):
    """Handle /settings /regions /threshold /help for a subscribed chat.

    Returns (reply, change) where change is a short description for the
    owner's report, or None if nothing changed.
    """
    chats = state["chats"]
    cid = str(chat_id)
    label = defaults["label"]
    if cmd == "/help":
        return help_text(defaults), None
    if cid not in chats:
        return "This chat isn't subscribed. Send /start first.", None
    if cmd in ("/regions", "/addregion", "/removeregion"):
        given, err = parse_regions(args)
        if err:
            example = {"/regions": "/regions west central",
                       "/addregion": "/addregion north",
                       "/removeregion": "/removeregion west"}[cmd]
            err = err.replace("/regions west central", example)
            return f"{html.escape(err)}. Options: north, south, east, west, central, or all.", None
        current, _ = chat_settings(state, cid, defaults)
        if cmd == "/addregion":
            regions = list(dict.fromkeys(current + given))
        elif cmd == "/removeregion":
            regions = [r for r in current if r not in given]
            if not regions:
                return ("A chat needs at least one region. Use /regions to pick "
                        "others, or /stop to turn alerts off."), None
        else:
            regions = given
        chats[cid]["regions"] = regions
        change = "regions to " + ", ".join(r.title() for r in regions)
    elif cmd == "/threshold":
        threshold, err = parse_threshold(args)
        if err:
            return f"{html.escape(err)}.", None
        chats[cid]["threshold"] = threshold
        change = f"threshold to {threshold:g}"
    else:  # /settings
        regions, threshold = chat_settings(state, cid, defaults)
        return (
            f"⚙️ This chat gets {describe_settings(regions, threshold, label)}.\n"
            "Change with /regions, /addregion, /removeregion or /threshold."
        ), None
    regions, threshold = chat_settings(state, cid, defaults)
    return f"✅ Updated: this chat now gets {describe_settings(regions, threshold, label)}.", change


def process_updates(state, updates, max_chats=None):
    """Apply Telegram updates to the subscriber list.

    Returns events as (kind, chat, user, extra) where kind is one of
    joined / left / subscribed / unsubscribed / full / command. For
    "command", extra is (msg, command, args); otherwise None. New chats beyond
    `max_chats` are turned away ("full") so the bot can't be flooded.
    """
    chats = state["chats"]
    events = []

    def is_full(cid):
        return max_chats is not None and cid not in chats and len(chats) >= max_chats

    for u in updates:
        state["offset"] = max(state["offset"], u["update_id"] + 1)

        member = u.get("my_chat_member")
        if member:
            chat = member["chat"]
            cid = str(chat["id"])
            status = member["new_chat_member"]["status"]
            if status in ("member", "administrator"):
                if is_full(cid):
                    events.append(("full", chat, member.get("from"), None))
                elif cid not in chats:
                    chats[cid] = {"type": chat["type"]}
                    events.append(("joined", chat, member.get("from"), None))
            elif status in ("left", "kicked"):
                chats.pop(cid, None)
                events.append(("left", chat, member.get("from"), None))
            continue

        msg = u.get("message")
        if not msg:
            continue
        chat = msg["chat"]
        cid = str(chat["id"])
        if msg.get("migrate_to_chat_id"):  # group upgraded to supergroup
            new = str(msg["migrate_to_chat_id"])
            old = chats.pop(cid, None)
            if old is not None:
                chats[new] = {**old, "type": "supergroup"}
            continue
        cmd, args = _command(msg.get("text"))
        if cmd == "/start":
            if is_full(cid):
                events.append(("full", chat, msg.get("from"), None))
                continue
            chats.setdefault(cid, {"type": chat["type"]})
            events.append(("subscribed", chat, msg.get("from"), None))
        elif cmd == "/stop":
            chats.pop(cid, None)
            events.append(("unsubscribed", chat, msg.get("from"), None))
        elif cmd in SETTINGS_COMMANDS:
            events.append(("command", chat, msg.get("from"), (msg, cmd, args)))
    return events


def _chat_name(chat):
    if chat.get("type") == "private":
        return "private chat"
    return f'{chat.get("type", "group")} "{chat.get("title", chat["id"])}"'


def _user_name(user):
    if not user:
        return "someone"
    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
    if user.get("username"):
        name += f" (@{user['username']})"
    return name or str(user.get("id"))


def owner_report(events):
    icons = {"joined": "➕", "left": "➖", "subscribed": "🔔", "unsubscribed": "🔕", "full": "⛔",
             "changed": "⚙️"}
    verbs = {
        "joined": "added the bot to",
        "left": "removed the bot from",
        "subscribed": "sent /start in",
        "unsubscribed": "sent /stop in",
        "full": "was turned away (subscriber limit reached) in",
    }
    lines = []
    for kind, chat, user, extra in events:
        verb = f"set {extra} in" if kind == "changed" else verbs[kind]
        lines.append(
            f"{icons[kind]} {html.escape(_user_name(user), quote=False)} {verb} "
            f"{html.escape(_chat_name(chat), quote=False)}"
        )
    return "<b>Haze bot activity</b>\n" + "\n".join(lines)


ANONYMOUS_ADMIN_BOT = 1087968824  # Telegram's "Group" sender for anonymous admins


def is_group_admin(token, msg):
    chat = msg["chat"]
    if chat["type"] not in ("group", "supergroup"):
        return True  # private chat: it's their own setting
    if (msg.get("sender_chat") or {}).get("id") == chat["id"]:
        return True  # sent by an anonymous admin
    user = msg.get("from") or {}
    if user.get("id") == ANONYMOUS_ADMIN_BOT:
        return True
    member = call(token, "getChatMember", chat_id=chat["id"], user_id=user.get("id"))
    return member.get("status") in ("creator", "administrator")


def sync(token, state_path, owner_chat_id, defaults, max_chats=None):
    """Pull new updates, update the list and settings, reply, tell the owner.

    `defaults` has "regions", "threshold" and "label". Returns the updated
    state (already saved).
    """
    state = load_state(state_path)
    if state.get("commands_version") != COMMANDS_VERSION:
        call(token, "setMyCommands",
             commands=[{"command": c, "description": d} for c, d in BOT_COMMANDS])
        call(token, "setMyShortDescription", short_description=BOT_SHORT_DESCRIPTION)
        call(token, "setMyDescription", description=BOT_DESCRIPTION)
        state["commands_version"] = COMMANDS_VERSION
    updates = call(
        token, "getUpdates",
        offset=state["offset"],
        timeout=0,
        allowed_updates=["message", "my_chat_member"],
    )
    events = process_updates(state, updates, max_chats)

    report = []
    for kind, chat, user, extra in events:
        text = None
        if kind in ("joined", "subscribed"):
            regions, threshold = chat_settings(state, chat["id"], defaults)
            text = (
                f"👋 This chat will get haze {describe_settings(regions, threshold, defaults['label'])} "
                "(checked hourly, data from NEA).\n"
                "Send /settings to change this, or /stop to turn alerts off."
            )
        elif kind == "unsubscribed":
            text = "🔕 Haze alerts stopped here. Send /start to turn them back on."
        elif kind == "full":
            text = "Sorry, this haze bot isn't taking new chats right now."
        elif kind == "command":
            msg, cmd, args = extra
            try:
                allowed = cmd not in CHANGE_COMMANDS or is_group_admin(token, msg)
            except TelegramError as e:
                print(f"Couldn't check admin status in a {chat.get('type')} chat: {e}")
                allowed = False
            if allowed:
                text, change = apply_command(state, chat["id"], cmd, args, defaults)
                if change:
                    report.append(("changed", chat, user, change))
            else:
                text = "Only group admins can change the alert settings."
        if kind != "command":
            report.append((kind, chat, user, extra))
        if text:
            try:
                send_message(token, chat["id"], text)
            except TelegramError as e:
                print(f"Couldn't reply to a {chat.get('type')} chat: {e}")
    save_state(state_path, state)
    if report and owner_chat_id:
        send_message(token, owner_chat_id, owner_report(report))

    counts = {}
    for kind, _, _, _ in events:
        counts[kind] = counts.get(kind, 0) + 1
    print(f"Telegram: {len(state['chats'])} subscribed chats; new activity: {counts or 'none'}")
    return state


def broadcast(token, state, state_path, extra_chat_ids, text):
    """Send to every chat in state["chats"] plus any fixed chat IDs.

    `text` is a string, or a function chat_id -> string/None so each chat can
    get its own message (None = nothing to send to that chat). Chats that
    removed/blocked the bot are dropped from the list. Returns the number of
    chats that failed for other reasons.
    """
    text_for = text if callable(text) else (lambda _cid: text)
    chats = state["chats"]
    targets = list(dict.fromkeys(list(extra_chat_ids) + list(chats)))
    sent = skipped = failed = 0
    for cid in targets:
        body = text_for(cid)
        if body is None:
            skipped += 1
            continue
        try:
            try:
                send_message(token, cid, body)
            except TelegramError as e:
                if not e.migrate_to:
                    raise
                new = str(e.migrate_to)
                old = chats.pop(cid, None)
                if old is not None:
                    chats[new] = {**old, "type": "supergroup"}
                send_message(token, new, body)
            sent += 1
        except TelegramError as e:
            if e.chat_gone and cid in chats:
                chats.pop(cid)
                print(f"Dropped a chat that removed or blocked the bot ({e.description}).")
            else:
                print(f"Telegram send failed: {e}")
                failed += 1
    if state_path:
        save_state(state_path, state)
    print(f"Telegram: sent to {sent} chat(s), {skipped} below their limit, {failed} failed.")
    return failed
