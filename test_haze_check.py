import unittest

from haze_check import latest_reading

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
        value, ts = latest_reading(SAMPLE, "pm25_one_hourly", "west")
        self.assertEqual(value, 61)
        self.assertEqual(ts, "2026-09-30T10:00:00+08:00")

    def test_psi_metric(self):
        value, _ = latest_reading(SAMPLE, "psi_twenty_four_hourly", "west")
        self.assertEqual(value, 52)

    def test_empty_items_raises(self):
        with self.assertRaises(ValueError):
            latest_reading({"data": {"items": []}}, "pm25_one_hourly", "west")


if __name__ == "__main__":
    unittest.main()
