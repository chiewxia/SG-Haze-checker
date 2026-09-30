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
    """'/start@HazeBot hi' -> '/start'."""
    first = (text or "").split(maxsplit=1)[:1]
    return first[0].split("@")[0].lower() if first else ""


def process_updates(state, updates):
    """Apply Telegram updates to the subscriber list.

    Returns events as (kind, chat, user) where kind is one of
    joined / left / subscribed / unsubscribed.
    """
    chats = state["chats"]
    events = []
    for u in updates:
        state["offset"] = max(state["offset"], u["update_id"] + 1)

        member = u.get("my_chat_member")
        if member:
            chat = member["chat"]
            cid = str(chat["id"])
            status = member["new_chat_member"]["status"]
            if status in ("member", "administrator"):
                if cid not in chats:
                    chats[cid] = {"type": chat["type"]}
                    events.append(("joined", chat, member.get("from")))
            elif status in ("left", "kicked"):
                chats.pop(cid, None)
                events.append(("left", chat, member.get("from")))
            continue

        msg = u.get("message")
        if not msg:
            continue
        chat = msg["chat"]
        cid = str(chat["id"])
        if msg.get("migrate_to_chat_id"):  # group upgraded to supergroup
            new = str(msg["migrate_to_chat_id"])
            if chats.pop(cid, None) is not None:
                chats[new] = {"type": "supergroup"}
            continue
        cmd = _command(msg.get("text"))
        if cmd == "/start":
            chats.setdefault(cid, {"type": chat["type"]})
            events.append(("subscribed", chat, msg.get("from")))
        elif cmd == "/stop":
            chats.pop(cid, None)
            events.append(("unsubscribed", chat, msg.get("from")))
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
    icons = {"joined": "➕", "left": "➖", "subscribed": "🔔", "unsubscribed": "🔕"}
    verbs = {
        "joined": "added the bot to",
        "left": "removed the bot from",
        "subscribed": "sent /start in",
        "unsubscribed": "sent /stop in",
    }
    lines = [
        f"{icons[kind]} {html.escape(_user_name(user), quote=False)} {verbs[kind]} "
        f"{html.escape(_chat_name(chat), quote=False)}"
        for kind, chat, user in events
    ]
    return "<b>Haze bot activity</b>\n" + "\n".join(lines)


def sync(token, state_path, owner_chat_id, welcome):
    """Pull new updates, update the list, greet new chats, tell the owner.

    Returns the updated state (already saved).
    """
    state = load_state(state_path)
    updates = call(
        token, "getUpdates",
        offset=state["offset"],
        timeout=0,
        allowed_updates=["message", "my_chat_member"],
    )
    events = process_updates(state, updates)
    save_state(state_path, state)

    for kind, chat, _ in events:
        text = {
            "joined": welcome,
            "subscribed": welcome,
            "unsubscribed": "🔕 Haze alerts stopped here. Send /start to turn them back on.",
        }.get(kind)
        if text:
            try:
                send_message(token, chat["id"], text)
            except TelegramError as e:
                print(f"Couldn't reply to a {chat.get('type')} chat: {e}")
    if events and owner_chat_id:
        send_message(token, owner_chat_id, owner_report(events))

    counts = {}
    for kind, _, _ in events:
        counts[kind] = counts.get(kind, 0) + 1
    print(f"Telegram: {len(state['chats'])} subscribed chats; new activity: {counts or 'none'}")
    return state


def broadcast(token, state, state_path, extra_chat_ids, text):
    """Send to every chat in state["chats"] plus any fixed chat IDs.

    Chats that removed/blocked the bot are dropped from the list. Returns the
    number of chats that failed for other reasons.
    """
    chats = state["chats"]
    targets = list(dict.fromkeys(list(extra_chat_ids) + list(chats)))
    sent = failed = 0
    for cid in targets:
        try:
            try:
                send_message(token, cid, text)
            except TelegramError as e:
                if not e.migrate_to:
                    raise
                new = str(e.migrate_to)
                if chats.pop(cid, None) is not None:
                    chats[new] = {"type": "supergroup"}
                send_message(token, new, text)
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
    print(f"Telegram: sent to {sent} chat(s), {failed} failed.")
    return failed
