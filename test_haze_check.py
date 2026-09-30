import unittest
from datetime import datetime, timezone

from haze_check import (
    build_channels,
    format_time,
    is_current_hour,
    latest_reading,
    make_alert,
    region_summary,
    telegram_text,
)

SAMPLE = {
    "code": 0,
    "data": {
        "items": [
            {
                "timestamp": "2026-09-30T09:00:00+08:00",
                "readings": {
                    "pm25_one_hourly": {"west": 12, "east": 9, "central": 10, "north": 8, "south": 11},
                    "psi_twenty_four_hourly": {"west": 48, "east": 40, "central": 44, "north": 39, "south": 42},
                },
            },
            {
                "timestamp": "2026-09-30T10:00:00+08:00",
                "readings": {
                    "pm25_one_hourly": {"west": 61, "east": 9, "central": 10, "north": 8, "south": 11},
                    "psi_twenty_four_hourly": {"west": 52, "east": 40, "central": 44, "north": 39, "south": 42},
                },
            },
        ]
    },
}


class LatestReadingTest(unittest.TestCase):
    def test_uses_latest_item(self):
        ts, all_regions = latest_reading(SAMPLE, "pm25_one_hourly", ["west", "central"])
        self.assertEqual(all_regions["west"], 61)
        self.assertEqual(ts, "2026-09-30T10:00:00+08:00")
        self.assertEqual(all_regions["east"], 9)

    def test_psi_metric(self):
        _, all_regions = latest_reading(SAMPLE, "psi_twenty_four_hourly", ["west"])
        self.assertEqual(all_regions["west"], 52)

    def test_missing_metric_raises_with_payload(self):
        with self.assertRaisesRegex(ValueError, "psi_twenty_four_hourly"):
            latest_reading(SAMPLE, "o3_sub_index", ["west"])

    def test_empty_items_raises(self):
        with self.assertRaises(ValueError):
            latest_reading({"data": {"items": []}}, "pm25_one_hourly", ["west"])


class MessageFormatTest(unittest.TestCase):
    def test_region_summary_puts_watched_regions_first_and_flags_high(self):
        text = region_summary(
            {"west": 61, "east": 9, "central": 10, "north": 58, "south": 11},
            ["west", "central"],
            55,
        )
        self.assertEqual(
            text.splitlines(),
            ["West: 61 ⚠️", "Central: 10", "North: 58 ⚠️", "South: 11", "East: 9"],
        )

    def test_format_time(self):
        self.assertEqual(format_time("2026-09-30T18:00:00+08:00"), "6pm")
        self.assertEqual(format_time("2026-09-30T00:00:00+08:00"), "12am")
        self.assertEqual(format_time("2026-09-30T12:00:00+08:00"), "12pm")


class MakeAlertTest(unittest.TestCase):
    READINGS = {"west": 61, "east": 9, "central": 58, "north": 70, "south": 11}

    def test_alert_lists_high_watched_regions(self):
        title, message = make_alert(self.READINGS, ["west", "central"], 55, "1-hr PM2.5", "µg/m³", "7pm")
        self.assertEqual(title, "Haze alert: West 61, Central 58")
        self.assertTrue(message.startswith("West & Central are above your limit of 55."))

    def test_per_chat_settings(self):
        self.assertIsNone(make_alert(self.READINGS, ["east"], 55, "x", "", "7pm"))
        title, _ = make_alert(self.READINGS, ["west", "central"], 60, "x", "", "7pm")
        self.assertEqual(title, "Haze alert: West 61")


class ChannelsTest(unittest.TestCase):
    def test_ntfy_only(self):
        names = [n for n, _ in build_channels({"NTFY_TOPIC": "t"})]
        self.assertEqual(names, ["ntfy"])

    def test_ntfy_and_telegram(self):
        channels = dict(build_channels({
            "NTFY_TOPIC": "t",
            "TELEGRAM_BOT_TOKEN": "tok",
            "TELEGRAM_CHAT_ID": "123, -456",
            "TELEGRAM_STATE": "/nonexistent/state.json",
        }))
        self.assertEqual(list(channels), ["ntfy", "telegram"])
        self.assertEqual(channels["telegram"].chat_ids, ["123", "-456"])

    def test_telegram_token_alone_is_enough(self):
        names = [n for n, _ in build_channels({
            "TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_STATE": "/nonexistent/s.json"
        })]
        self.assertEqual(names, ["telegram"])

    def test_chat_id_without_token_exits(self):
        with self.assertRaises(SystemExit):
            build_channels({"TELEGRAM_CHAT_ID": "123"})

    def test_nothing_configured(self):
        self.assertEqual(build_channels({}), [])

    def test_telegram_text_escapes_html(self):
        text = telegram_text("Alert <1>", "a & b")
        self.assertIn("<b>Alert &lt;1&gt;</b>", text)
        self.assertIn("a &amp; b", text)


class NtfyUnaffectedByChatSettingsTest(unittest.TestCase):
    def test_ntfy_uses_defaults_even_when_a_chat_customised(self):
        import os
        import tempfile
        from datetime import timedelta
        from unittest import mock

        import haze_check
        import telegram_subs

        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        ts = now.astimezone(timezone(timedelta(hours=8))).isoformat()
        readings = {"west": 10, "central": 10, "north": 10, "south": 10, "east": 90}
        ntfy_sent, tg_sent = [], []
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            # One chat switched itself to East; ntfy should still follow West/Central.
            telegram_subs.save_state(path, {"offset": 0, "commands_version": 2,
                                            "chats": {"-100": {"type": "group", "regions": ["east"]}}})
            env = {"NTFY_TOPIC": "t", "TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_STATE": path}

            def fake_call(token, method, **p):
                if method == "sendMessage":
                    tg_sent.append(str(p["chat_id"]))
                return [] if method == "getUpdates" else True

            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(haze_check, "fetch", lambda u: {"data": {"items": [
                        {"timestamp": ts, "readings": {"pm25_one_hourly": readings}}]}}), \
                    mock.patch.object(haze_check, "send_ntfy", lambda *a: ntfy_sent.append(a)), \
                    mock.patch.object(telegram_subs, "call", fake_call):
                haze_check.main()
        self.assertEqual(tg_sent, ["-100"])  # the East chat is alerted
        self.assertEqual(ntfy_sent, [])  # ntfy (West/Central) is not


class DuplicateRunTest(unittest.TestCase):
    def test_second_run_for_same_reading_sends_nothing(self):
        import os
        import tempfile
        from datetime import timedelta
        from unittest import mock

        import haze_check
        import telegram_subs

        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        ts = now.astimezone(timezone(timedelta(hours=8))).isoformat()
        readings = {"west": 61, "central": 10, "north": 10, "south": 10, "east": 10}
        sent = []
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            telegram_subs.save_state(path, {"offset": 0, "commands_version": telegram_subs.COMMANDS_VERSION,
                                            "chats": {"-100": {"type": "group"}}})
            env = {"NTFY_TOPIC": "t", "TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_STATE": path}

            def fake_call(token, method, **p):
                if method == "sendMessage":
                    sent.append("telegram")
                return [] if method == "getUpdates" else True

            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(haze_check, "fetch", lambda u: {"data": {"items": [
                        {"timestamp": ts, "readings": {"pm25_one_hourly": readings}}]}}), \
                    mock.patch.object(haze_check, "send_ntfy", lambda *a: sent.append("ntfy")), \
                    mock.patch.object(telegram_subs, "call", fake_call):
                haze_check.main()
                self.assertEqual(sorted(sent), ["ntfy", "telegram"])
                haze_check.main()  # e.g. GitHub's schedule firing after cron-job.org
        self.assertEqual(sorted(sent), ["ntfy", "telegram"])  # nothing new


class SettingTest(unittest.TestCase):
    def test_blank_or_missing_uses_code_default(self):
        from haze_check import DEFAULTS, setting
        self.assertEqual(setting("THRESHOLD", {}), DEFAULTS["THRESHOLD"])
        self.assertEqual(setting("THRESHOLD", {"THRESHOLD": ""}), DEFAULTS["THRESHOLD"])
        self.assertEqual(setting("THRESHOLD", {"THRESHOLD": " 60 "}), "60")


class IsCurrentHourTest(unittest.TestCase):
    # 10:07 SGT == 02:07 UTC
    NOW = datetime(2026, 9, 30, 2, 7, tzinfo=timezone.utc)

    def test_this_hours_reading_is_fresh(self):
        self.assertTrue(is_current_hour("2026-09-30T10:00:00+08:00", self.NOW))

    def test_last_hours_reading_is_stale(self):
        self.assertFalse(is_current_hour("2026-09-30T09:00:00+08:00", self.NOW))

    def test_utc_z_suffix(self):
        self.assertTrue(is_current_hour("2026-09-30T02:00:00Z", self.NOW))

    def test_bad_timestamp_is_stale(self):
        self.assertFalse(is_current_hour("", self.NOW))


if __name__ == "__main__":
    unittest.main()
