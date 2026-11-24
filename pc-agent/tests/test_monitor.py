from __future__ import annotations

import unittest

from framepulse_agent.monitor import (
    LIVE_UPDATE_INTERVAL_SECONDS,
    STATE_CAPTURING,
    STATE_ERROR,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_STARTING,
    AgentStatus,
)


class LiveUpdateIntervalTests(unittest.TestCase):
    def test_live_status_is_refreshed_within_five_seconds(self) -> None:
        self.assertLessEqual(LIVE_UPDATE_INTERVAL_SECONDS, 5.0)


class AgentStatusTitleTests(unittest.TestCase):
    def test_idle(self) -> None:
        self.assertEqual(AgentStatus().title, "Waiting for a game")

    def test_capturing_shows_live_fps(self) -> None:
        status = AgentStatus(state=STATE_CAPTURING, game="Hades", live_fps=143.6)
        self.assertEqual(status.title, "Hades – 144 FPS")

    def test_capturing_without_frames_yet(self) -> None:
        status = AgentStatus(state=STATE_CAPTURING, game="Hades")
        self.assertEqual(status.title, "Hades – measuring")

    def test_starting(self) -> None:
        status = AgentStatus(state=STATE_STARTING, game="Hades")
        self.assertEqual(status.title, "Hades – starting")

    def test_paused(self) -> None:
        self.assertEqual(AgentStatus(state=STATE_PAUSED).title, "Paused")

    def test_error(self) -> None:
        self.assertEqual(AgentStatus(state=STATE_ERROR).title, "Measurement error")

    def test_idle_is_not_error_even_with_past_error(self) -> None:
        status = AgentStatus(state=STATE_IDLE, last_error="old error")
        self.assertEqual(status.title, "Waiting for a game")


if __name__ == "__main__":
    unittest.main()
