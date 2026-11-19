from __future__ import annotations

import unittest

from framepulse_agent.metrics import FrameAggregator


class FrameAggregatorTests(unittest.TestCase):
    def test_basic_sample_and_metrics(self) -> None:
        aggregator = FrameAggregator(sample_seconds=1.0, warmup_seconds=0.0)
        for _ in range(100):
            aggregator.add_frame(10.0)

        samples = aggregator.samples()
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0], (0.0, 100.0))

        metrics = aggregator.metrics()
        self.assertEqual(metrics.frame_count, 100)
        self.assertAlmostEqual(metrics.duration_seconds, 1.0, places=3)
        self.assertAlmostEqual(metrics.avg_fps, 100.0, places=3)
        self.assertAlmostEqual(metrics.min_fps, 100.0, places=3)
        self.assertAlmostEqual(metrics.max_fps, 100.0, places=3)
        self.assertTrue(metrics.is_usable)

    def test_warmup_frames_are_ignored(self) -> None:
        aggregator = FrameAggregator(sample_seconds=1.0, warmup_seconds=0.5)
        for _ in range(100):
            aggregator.add_frame(10.0)

        self.assertEqual(aggregator.frame_count(), 50)
        self.assertAlmostEqual(aggregator.duration_seconds(), 0.5, places=3)

        aggregator.finish()
        samples = aggregator.samples()
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0][0], 0.0)
        self.assertAlmostEqual(samples[0][1], 100.0, places=3)

        metrics = aggregator.metrics()
        self.assertAlmostEqual(metrics.avg_fps, 100.0, places=3)
        self.assertAlmostEqual(metrics.duration_seconds, 0.5, places=3)
        self.assertAlmostEqual(metrics.total_seconds, 1.0, places=3)

    def test_one_percent_low(self) -> None:
        aggregator = FrameAggregator(sample_seconds=60.0, warmup_seconds=0.0)
        for _ in range(99):
            aggregator.add_frame(5.0)
        aggregator.add_frame(100.0)

        metrics = aggregator.metrics()
        self.assertEqual(metrics.frame_count, 100)
        self.assertAlmostEqual(metrics.min_fps, 10.0, places=3)
        self.assertGreater(metrics.avg_fps, 150.0)

    def test_max_fps_uses_best_sample(self) -> None:
        aggregator = FrameAggregator(sample_seconds=1.0, warmup_seconds=0.0)
        for _ in range(100):
            aggregator.add_frame(10.0)  # 100 FPS
        for _ in range(200):
            aggregator.add_frame(5.0)  # 200 FPS

        metrics = aggregator.metrics()
        self.assertAlmostEqual(metrics.max_fps, 200.0, places=3)
        self.assertEqual(len(aggregator.samples()), 2)

    def test_invalid_frames_are_ignored(self) -> None:
        aggregator = FrameAggregator(sample_seconds=1.0, warmup_seconds=0.0)
        self.assertFalse(aggregator.add_frame(0.0))
        self.assertFalse(aggregator.add_frame(-5.0))
        self.assertFalse(aggregator.add_frame(20_000.0))
        self.assertEqual(aggregator.frame_count(), 0)

        metrics = aggregator.metrics()
        self.assertFalse(metrics.is_usable)
        self.assertFalse(metrics.as_session_values()["duration_seconds"])

    def test_unfinished_sample_needs_minimum_fill(self) -> None:
        aggregator = FrameAggregator(sample_seconds=2.0, warmup_seconds=0.0)
        aggregator.add_frame(10.0)  # příliš krátký zbytek
        aggregator.finish()
        self.assertEqual(aggregator.samples(), [])

    def test_session_values_rounding(self) -> None:
        aggregator = FrameAggregator(sample_seconds=10.0, warmup_seconds=0.0)
        for _ in range(3):
            aggregator.add_frame(16.0)

        values = aggregator.metrics().as_session_values()
        self.assertEqual(values["duration_seconds"], 0)
        self.assertIn("avg_fps", values)
        self.assertIn("min_fps", values)
        self.assertIn("max_fps", values)


if __name__ == "__main__":
    unittest.main()
