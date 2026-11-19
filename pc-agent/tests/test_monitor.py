from __future__ import annotations

import unittest

from framepulse_agent.monitor import (
    STATE_CAPTURING,
    STATE_ERROR,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_STARTING,
    AgentStatus,
)


class AgentStatusTitleTests(unittest.TestCase):
    def test_idle(self) -> None:
        self.assertEqual(AgentStatus().title, "Čekám na hru")

    def test_capturing_shows_live_fps(self) -> None:
        status = AgentStatus(state=STATE_CAPTURING, game="Hades", live_fps=143.6)
        self.assertEqual(status.title, "Hades – 144 FPS")

    def test_capturing_without_frames_yet(self) -> None:
        status = AgentStatus(state=STATE_CAPTURING, game="Hades")
        self.assertEqual(status.title, "Hades – měřím")

    def test_starting(self) -> None:
        status = AgentStatus(state=STATE_STARTING, game="Hades")
        self.assertEqual(status.title, "Hades – spouštím")

    def test_paused(self) -> None:
        self.assertEqual(AgentStatus(state=STATE_PAUSED).title, "Pozastaveno")

    def test_error(self) -> None:
        self.assertEqual(AgentStatus(state=STATE_ERROR).title, "Chyba měření")

    def test_idle_is_not_error_even_with_past_error(self) -> None:
        status = AgentStatus(state=STATE_IDLE, last_error="stará chyba")
        self.assertEqual(status.title, "Čekám na hru")


if __name__ == "__main__":
    unittest.main()
