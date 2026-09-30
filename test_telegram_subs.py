import os
import tempfile
import unittest
from unittest import mock

import telegram_subs as tg
from telegram_subs import TelegramError

GROUP = {"id": -100, "type": "group", "title": "Family <3"}
DM = {"id": 42, "type": "private", "first_name": "Ann"}
ANN = {"id": 42, "first_name": "Ann", "username": "ann"}


def member_update(uid, chat, status, user=ANN):
    return {"update_id": uid, "my_chat_member": {
        "chat": chat, "from": user, "new_chat_member": {"status": status}}}


def message_update(uid, chat, text=None, **extra):
    msg = {"chat": chat, "from": ANN, **extra}
    if text is not None:
        msg["text"] = text
    return {"update_id": uid, "message": msg}


def empty_state():
    return {"offset": 0, "chats": {}}


class ProcessUpdatesTest(unittest.TestCase):
    def test_added_to_group_subscribes(self):
        state = empty_state()
        events = tg.process_updates(state, [member_update(5, GROUP, "member")])
        self.assertEqual(state["chats"], {"-100": {"type": "group"}})
        self.assertEqual(state["offset"], 6)
        self.assertEqual([e[0] for e in events], ["joined"])

    def test_removed_from_group_unsubscribes(self):
        state = {"offset": 0, "chats": {"-100": {"type": "group"}}}
        events = tg.process_updates(state, [member_update(1, GROUP, "kicked")])
        self.assertEqual(state["chats"], {})
        self.assertEqual([e[0] for e in events], ["left"])

    def test_start_and_stop_commands(self):
        state = empty_state()
        tg.process_updates(state, [message_update(1, DM, "/start")])
        self.assertIn("42", state["chats"])
        tg.process_updates(state, [message_update(2, GROUP, "/start@HazeBot")])
        self.assertIn("-100", state["chats"])
        tg.process_updates(state, [message_update(3, DM, "/stop")])
        self.assertNotIn("42", state["chats"])

    def test_other_messages_ignored(self):
        state = empty_state()
        events = tg.process_updates(state, [
            message_update(1, GROUP, "hello"), message_update(2, GROUP)])
        self.assertEqual((state["chats"], events), ({}, []))
        self.assertEqual(state["offset"], 3)

    def test_group_upgrade_moves_id(self):
        state = {"offset": 0, "chats": {"-100": {"type": "group"}}}
        tg.process_updates(state, [message_update(1, GROUP, migrate_to_chat_id=-1009)])
        self.assertEqual(state["chats"], {"-1009": {"type": "supergroup"}})


class OwnerReportTest(unittest.TestCase):
    def test_report_names_who_and_where_escaped(self):
        text = tg.owner_report([("joined", GROUP, ANN), ("subscribed", DM, ANN)])
        self.assertIn('➕ Ann (@ann) added the bot to group "Family &lt;3"', text)
        self.assertIn("🔔 Ann (@ann) sent /start in private chat", text)


class StateFileTest(unittest.TestCase):
    def test_round_trip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "s.json")
            self.assertEqual(tg.load_state(path), empty_state())
            tg.save_state(path, {"offset": 7, "chats": {"1": {"type": "private"}}})
            self.assertEqual(tg.load_state(path)["offset"], 7)


class BroadcastTest(unittest.TestCase):
    def run_broadcast(self, state, extra, errors):
        sent = []

        def fake_send(token, chat_id, text):
            err = errors.get(str(chat_id))
            if err:
                raise err
            sent.append(str(chat_id))

        with mock.patch.object(tg, "send_message", fake_send):
            failed = tg.broadcast("tok", state, None, extra, "hi")
        return sent, failed

    def test_sends_to_subscribers_and_fixed_ids_once(self):
        state = {"chats": {"1": {}, "2": {}}}
        sent, failed = self.run_broadcast(state, ["2", "3"], {})
        self.assertEqual((sorted(sent), failed), (["1", "2", "3"], 0))

    def test_drops_chats_that_removed_the_bot(self):
        state = {"chats": {"1": {}, "2": {}}}
        sent, failed = self.run_broadcast(
            state, [], {"2": TelegramError(403, "Forbidden: bot was kicked")})
        self.assertEqual((sent, failed, list(state["chats"])), (["1"], 0, ["1"]))

    def test_follows_supergroup_migration(self):
        state = {"chats": {"-1": {}}}
        sent, failed = self.run_broadcast(
            state, [], {"-1": TelegramError(400, "upgraded", migrate_to=-1009)})
        self.assertEqual((sent, failed, list(state["chats"])), (["-1009"], 0, ["-1009"]))

    def test_other_errors_count_as_failed(self):
        state = {"chats": {"1": {}}}
        sent, failed = self.run_broadcast(
            state, [], {"1": TelegramError(429, "Too Many Requests")})
        self.assertEqual((sent, failed, list(state["chats"])), ([], 1, ["1"]))

    def test_fixed_id_errors_are_not_dropped_silently(self):
        sent, failed = self.run_broadcast(
            {"chats": {}}, ["9"], {"9": TelegramError(403, "Forbidden")})
        self.assertEqual(failed, 1)


if __name__ == "__main__":
    unittest.main()
