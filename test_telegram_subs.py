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


class SubscriberLimitTest(unittest.TestCase):
    def test_new_chats_turned_away_when_full(self):
        state = {"offset": 0, "chats": {"1": {"type": "private"}}}
        events = tg.process_updates(state, [
            member_update(1, GROUP, "member"),
            message_update(2, DM, "/start"),
        ], max_chats=1)
        self.assertEqual(list(state["chats"]), ["1"])
        self.assertEqual([e[0] for e in events], ["full", "full"])

    def test_existing_chat_can_still_start_when_full(self):
        state = {"offset": 0, "chats": {"42": {"type": "private"}}}
        events = tg.process_updates(state, [message_update(1, DM, "/start")], max_chats=1)
        self.assertEqual([e[0] for e in events], ["subscribed"])


DEFAULTS = {"regions": ["west", "central"], "threshold": 55, "label": "1-hr PM2.5"}


class SettingsTest(unittest.TestCase):
    def test_parse_regions(self):
        self.assertEqual(tg.parse_regions("West, central")[0], ["west", "central"])
        self.assertEqual(tg.parse_regions("east east")[0], ["east"])
        self.assertEqual(len(tg.parse_regions("all")[0]), 5)
        self.assertIsNone(tg.parse_regions("jurong")[0])
        self.assertIsNone(tg.parse_regions("")[0])

    def test_parse_threshold(self):
        self.assertEqual(tg.parse_threshold(" 60 ")[0], 60)
        self.assertIsNone(tg.parse_threshold("high")[0])
        self.assertIsNone(tg.parse_threshold("0")[0])
        self.assertIsNone(tg.parse_threshold("9999")[0])

    def test_commands_change_only_that_chat(self):
        state = {"offset": 0, "chats": {"-100": {"type": "group"}, "42": {"type": "private"}}}
        reply, change = tg.apply_command(state, -100, "/regions", "east", DEFAULTS)
        self.assertIn("East", reply)
        self.assertEqual(change, "regions to East")
        tg.apply_command(state, -100, "/threshold", "70", DEFAULTS)
        self.assertEqual(tg.chat_settings(state, -100, DEFAULTS), (["east"], 70))
        self.assertEqual(tg.chat_settings(state, 42, DEFAULTS), (["west", "central"], 55))

    def test_add_and_remove_regions(self):
        state = {"offset": 0, "chats": {"42": {"type": "private"}}}
        tg.apply_command(state, 42, "/addregion", "north, west", DEFAULTS)
        self.assertEqual(tg.chat_settings(state, 42, DEFAULTS)[0], ["west", "central", "north"])
        tg.apply_command(state, 42, "/removeregion", "west", DEFAULTS)
        self.assertEqual(tg.chat_settings(state, 42, DEFAULTS)[0], ["central", "north"])

    def test_cannot_remove_every_region(self):
        state = {"offset": 0, "chats": {"42": {"type": "private"}}}
        reply, change = tg.apply_command(state, 42, "/removeregion", "west central", DEFAULTS)
        self.assertIn("at least one region", reply)
        self.assertIsNone(change)
        self.assertNotIn("regions", state["chats"]["42"])

    def test_bad_add_shows_matching_example(self):
        state = {"offset": 0, "chats": {"42": {"type": "private"}}}
        reply, _ = tg.apply_command(state, 42, "/addregion", "", DEFAULTS)
        self.assertIn("/addregion north", reply)

    def test_bad_input_changes_nothing(self):
        state = {"offset": 0, "chats": {"42": {"type": "private"}}}
        reply, change = tg.apply_command(state, 42, "/regions", "jurong", DEFAULTS)
        self.assertIn("Unknown region: jurong", reply)
        self.assertIsNone(change)
        self.assertEqual(state["chats"]["42"], {"type": "private"})

    def test_settings_and_unsubscribed(self):
        state = {"offset": 0, "chats": {"42": {"type": "private"}}}
        self.assertIn("West or Central", tg.apply_command(state, 42, "/settings", "", DEFAULTS)[0])
        self.assertIn("/start first", tg.apply_command(state, 7, "/regions", "east", DEFAULTS)[0])

    def test_command_events_and_migration_keeps_settings(self):
        state = {"offset": 0, "chats": {"-100": {"type": "group", "threshold": 70}}}
        events = tg.process_updates(state, [
            message_update(1, GROUP, "/threshold@HazeBot 80"),
            message_update(2, GROUP, "just chatting /threshold 1"),
            message_update(3, GROUP, migrate_to_chat_id=-1009),
        ])
        self.assertEqual([(e[0], e[3][1], e[3][2]) for e in events], [("command", "/threshold", "80")])
        self.assertEqual(state["chats"], {"-1009": {"type": "supergroup", "threshold": 70}})


class SyncTest(unittest.TestCase):
    def run_sync(self, updates, member_status="member", state=None):
        sent, calls = [], []

        def fake_call(token, method, **p):
            calls.append(method)
            if method == "getUpdates":
                return updates
            if method == "getChatMember":
                return {"status": member_status}
            if method == "sendMessage":
                sent.append((str(p["chat_id"]), p["text"]))
            return True

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            if state:
                tg.save_state(path, state)
            with mock.patch.object(tg, "call", fake_call):
                result = tg.sync("tok", path, "999", DEFAULTS)
        return result, sent, calls

    def test_non_admin_cannot_change_group_settings(self):
        state = {"offset": 0, "chats": {"-100": {"type": "group"}}, "commands_version": 2}
        result, sent, _ = self.run_sync(
            [message_update(1, GROUP, "/regions east")], member_status="member", state=state)
        self.assertNotIn("regions", result["chats"]["-100"])
        self.assertIn("Only group admins", sent[0][1])

    def test_admin_can_change_group_settings_and_owner_is_told(self):
        state = {"offset": 0, "chats": {"-100": {"type": "group"}}, "commands_version": 2}
        result, sent, _ = self.run_sync(
            [message_update(1, GROUP, "/regions east")], member_status="administrator", state=state)
        self.assertEqual(result["chats"]["-100"]["regions"], ["east"])
        self.assertIn("✅", sent[0][1])
        self.assertEqual(sent[1][0], "999")
        self.assertIn("set regions to East", sent[1][1])

    def test_non_admin_cannot_add_regions_either(self):
        state = {"offset": 0, "chats": {"-100": {"type": "group"}}, "commands_version": 2}
        result, sent, _ = self.run_sync(
            [message_update(1, GROUP, "/addregion north")], state=state)
        self.assertNotIn("regions", result["chats"]["-100"])
        self.assertIn("Only group admins", sent[0][1])

    def test_private_chat_needs_no_admin_check(self):
        state = {"offset": 0, "chats": {"42": {"type": "private"}}, "commands_version": 2}
        result, _, calls = self.run_sync([message_update(1, DM, "/threshold 60")], state=state)
        self.assertEqual(result["chats"]["42"]["threshold"], 60)
        self.assertNotIn("getChatMember", calls)

    def test_registers_command_menu_once(self):
        result, _, calls = self.run_sync([])
        self.assertIn("setMyCommands", calls)
        self.assertEqual(result["commands_version"], tg.COMMANDS_VERSION)


class OwnerReportTest(unittest.TestCase):
    def test_report_names_who_and_where_escaped(self):
        text = tg.owner_report([
            ("joined", GROUP, ANN, None), ("subscribed", DM, ANN, None),
            ("changed", GROUP, ANN, "threshold to 60"),
        ])
        self.assertIn('➕ Ann (@ann) added the bot to group "Family &lt;3"', text)
        self.assertIn("🔔 Ann (@ann) sent /start in private chat", text)
        self.assertIn('⚙️ Ann (@ann) set threshold to 60 in group "Family &lt;3"', text)


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

    def test_per_chat_text_and_skip(self):
        sent = []
        with mock.patch.object(tg, "send_message", lambda t, c, text: sent.append((c, text))):
            failed = tg.broadcast(
                "tok", {"chats": {"1": {}, "2": {}}}, None, [],
                lambda cid: None if cid == "2" else f"hi {cid}")
        self.assertEqual((sent, failed), ([("1", "hi 1")], 0))

    def test_fixed_id_errors_are_not_dropped_silently(self):
        sent, failed = self.run_broadcast(
            {"chats": {}}, ["9"], {"9": TelegramError(403, "Forbidden")})
        self.assertEqual(failed, 1)


if __name__ == "__main__":
    unittest.main()
