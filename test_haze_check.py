import unittest
from datetime import datetime, timezone

from haze_check import format_time, is_current_hour, latest_reading, region_summary

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
        value, ts, all_regions = latest_reading(SAMPLE, "pm25_one_hourly", "west")
        self.assertEqual(value, 61)
        self.assertEqual(ts, "2026-09-30T10:00:00+08:00")
        self.assertEqual(all_regions["east"], 9)

    def test_psi_metric(self):
        value, _, _ = latest_reading(SAMPLE, "psi_twenty_four_hourly", "west")
        self.assertEqual(value, 52)

    def test_missing_metric_raises_with_payload(self):
        with self.assertRaisesRegex(ValueError, "psi_twenty_four_hourly"):
            latest_reading(SAMPLE, "o3_sub_index", "west")

    def test_empty_items_raises(self):
        with self.assertRaises(ValueError):
            latest_reading({"data": {"items": []}}, "pm25_one_hourly", "west")


class MessageFormatTest(unittest.TestCase):
    def test_region_summary_puts_your_region_first_and_flags_high(self):
        text = region_summary(
            {"west": 61, "east": 9, "central": 10, "north": 58, "south": 11}, "west", 55
        )
        self.assertEqual(
            text.splitlines(),
            ["West: 61 ⚠️", "North: 58 ⚠️", "South: 11", "East: 9", "Central: 10"],
        )

    def test_format_time(self):
        self.assertEqual(format_time("2026-09-30T18:00:00+08:00"), "6pm")
        self.assertEqual(format_time("2026-09-30T00:00:00+08:00"), "12am")
        self.assertEqual(format_time("2026-09-30T12:00:00+08:00"), "12pm")


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
