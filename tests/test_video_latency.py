import unittest

from pc.measure_video_latency import stopwatch_ms, summarize
from pc.measure_timing import summarize as summarize_timing


class VideoLatencyTests(unittest.TestCase):
    def test_user_reading_is_10230_ms(self):
        self.assertEqual(stopwatch_ms("00:04:29.57") - stopwatch_ms("00:04:19.34"), 10230)

    def test_ambiguous_invalid_or_unreadable_readings_are_rejected(self):
        for text in ("", "OO:04:29.57", "00:60:00.00", "00:00:60.00",
                     "00:00:10.00 00:00:09.00"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                stopwatch_ms(text)

    def test_rejected_samples_do_not_become_zero_latency(self):
        result = summarize([{"elapsed_seconds": 0, "latency_ms": 10000},
                            {"elapsed_seconds": 10, "latency_ms": None},
                            {"elapsed_seconds": 20, "latency_ms": 12000}])
        self.assertEqual(result["latency_ms"], {"samples": 2, "median": 11000, "p95": 12000})
        self.assertEqual(result["rejected_samples"], 1)
        self.assertEqual(result["endpoint_drift_ms_per_second"], 100)

    def test_timing_drift_is_not_absolute_latency(self):
        result = summarize_timing([{"arrival_seconds": 2, "pts_seconds": 0},
                                   {"arrival_seconds": 12, "pts_seconds": 9.9}])
        self.assertAlmostEqual(result["drift_ms_per_second"], 10)
        self.assertIsNone(result["absolute_latency_ms"])


if __name__ == "__main__":
    unittest.main()
