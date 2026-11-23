from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from framepulse_agent import sensors
from framepulse_agent.config import Config
from framepulse_agent.metrics import FrameAggregator
from framepulse_agent.monitor import STATE_CAPTURING, GameAgent, _Active
from framepulse_agent.sensors import CpuStats, GpuStats
from framepulse_agent.supabase import SupabaseClient
from framepulse_agent.upload import SessionRecord


class FakeResponse:
    def __init__(self, status: int = 200, payload=b"[]") -> None:
        self.status_code = status
        self.content = payload
        self.text = payload.decode("utf-8")

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return json.loads(self.content)


class FakeSession:
    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[dict] = []
        self._responses = responses or []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self._responses.pop(0) if self._responses else FakeResponse()

    def close(self) -> None:
        pass


class FakeLiveClient:
    """SupabaseClient stand-in recording the `live_status` rows it receives."""

    def __init__(self) -> None:
        self.live_status: list[dict] = []
        self.sessions: list[dict] = []
        self.games: dict[str, dict] = {}

    def upsert_live_status(self, row) -> None:
        self.live_status.append(dict(row))

    def create_session(self, **kwargs) -> None:
        self.sessions.append(kwargs)

    def find_game(self, process_name):
        return self.games.get(process_name)

    def create_game(self, name, process_name):
        row = {"id": "00000000-0000-0000-0000-000000000000", "name": name, "process_name": process_name}
        self.games[process_name] = row
        return row

    def list_games(self):
        return []


class FakeUploader:
    def __init__(self, client: FakeLiveClient) -> None:
        self._client = client
        self.saved: list[SessionRecord] = []

    @property
    def client(self) -> FakeLiveClient:
        return self._client

    def save(self, record: SessionRecord, path: Path | None = None) -> Path:
        self.saved.append(record)
        return Path("outbox") / "fake.json"

    def pending_count(self) -> int:
        return 0


def make_config() -> Config:
    return Config(
        supabase_url="https://example.supabase.co",
        supabase_key="key",
        presentmon_path=Path("tools/PresentMon.exe"),
        data_dir=Path("C:/framepulse-test"),
        poll_interval=2.0,
        sample_interval=2.0,
        min_session_seconds=1,
        warmup_seconds=5.0,
        confirm_frames_seconds=90,
        stall_seconds=600,
        no_game_cooldown_seconds=900,
        preflight_on_start=False,
        notifications=False,
        notify_on_upload=False,
        upload_chunk_size=500,
        request_timeout=20,
    )


def make_active(agent: GameAgent) -> _Active:
    aggregator = FrameAggregator(sample_seconds=2.0, warmup_seconds=5.0)
    return _Active(
        pid=4242,
        process_name="game.exe",
        exe_path="C:/Games/Game/game.exe",
        title="Game",
        create_time=None,
        started_at=datetime.now(timezone.utc),
        aggregator=aggregator,
        start_monotonic=0.0,
        resolution="2560x1440",
        display_mode="Fullscreen",
        graphics_api="DX11",
        game_settings={"vsync": True, "fps_limit": 144},
    )


class LiveStatusClientTests(unittest.TestCase):
    def test_upsert_live_status_patches_the_singleton(self) -> None:
        session = FakeSession([FakeResponse(200, b'[{"id":"default"}]')])
        client = SupabaseClient("https://example.supabase.co", "key", session=session)

        client.upsert_live_status(
            {
                "id": "default",
                "is_playing": True,
                "game_name": "Game",
                "process_name": "game.exe",
                "started_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        )

        call = session.calls[0]
        self.assertEqual(call["method"], "PATCH")
        self.assertEqual(call["url"], "https://example.supabase.co/rest/v1/live_status")
        self.assertEqual(call["params"]["id"], "eq.default")
        self.assertTrue(call["json"]["is_playing"])
        self.assertEqual(call["json"]["game_name"], "Game")
        self.assertEqual(call["json"]["process_name"], "game.exe")

    def test_upsert_live_status_inserts_when_row_is_missing(self) -> None:
        session = FakeSession([FakeResponse(200, b"[]"), FakeResponse(201, b'[{"id":"default"}]')])
        client = SupabaseClient("https://example.supabase.co", "key", session=session)

        client.upsert_live_status({"id": "default", "is_playing": False})

        self.assertEqual([call["method"] for call in session.calls], ["PATCH", "POST"])
        self.assertEqual(session.calls[1]["json"]["id"], "default")
        self.assertFalse(session.calls[1]["json"]["is_playing"])


class AgentLiveStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeLiveClient()
        self.uploader = FakeUploader(self.client)
        self.agent = GameAgent(make_config(), self.uploader)

    def test_live_status_row_when_playing(self) -> None:
        active = make_active(self.agent)
        self.agent._live_status(active, is_playing=True)

        row = self.client.live_status[0]
        self.assertEqual(row["id"], "default")
        self.assertTrue(row["is_playing"])
        self.assertEqual(row["game_name"], "Game")
        self.assertEqual(row["process_name"], "game.exe")
        self.assertIsNotNone(row["started_at"])
        self.assertEqual(row["resolution"], "2560x1440")
        self.assertEqual(row["graphics_api"], "DX11")

    def test_live_status_row_when_stopped_is_zeroed(self) -> None:
        active = make_active(self.agent)
        self.agent._live_status(active, is_playing=True, current_fps=60.0, gpu_temp=55.0, cpu_temp=61.0, gpu_load=10.0, cpu_load=20.0)
        self.agent._live_status(active, is_playing=False)

        row = self.client.live_status[-1]
        self.assertFalse(row["is_playing"])
        self.assertIsNone(row["current_fps"])
        self.assertIsNone(row["gpu_temp"])
        self.assertIsNone(row["cpu_temp"])
        self.assertIsNone(row["gpu_load"])
        self.assertIsNone(row["cpu_load"])
        self.assertIsNone(row["resolution"])
        self.assertIsNone(row["graphics_api"])

    def test_live_update_records_fps_and_telemetry(self) -> None:
        active = make_active(self.agent)
        with mock.patch.object(sensors, "read_gpu_stats", return_value=GpuStats(temp_c=55.0, load_percent=10.0)), \
                mock.patch.object(sensors, "read_cpu_stats", return_value=CpuStats(temp_c=60.0, load_percent=20.0)):
            self.agent._live_update(active)

        row = self.client.live_status[-1]
        self.assertTrue(row["is_playing"])
        self.assertEqual(row["gpu_temp"], 55.0)
        self.assertEqual(row["cpu_temp"], 60.0)
        self.assertEqual(row["gpu_load"], 10.0)
        self.assertEqual(row["cpu_load"], 20.0)
        self.assertEqual(active.telemetry.summary()["gpu_temp_avg"], 55.0)
        self.assertEqual(active.telemetry.summary()["gpu_load_avg"], 10.0)
        self.assertEqual(active.telemetry.summary()["cpu_temp_avg"], 60.0)
        self.assertEqual(active.telemetry.summary()["cpu_load_avg"], 20.0)

    def test_live_update_telemetry_reaches_samples(self) -> None:
        active = make_active(self.agent)
        with mock.patch.object(sensors, "read_gpu_stats", return_value=GpuStats(temp_c=55.0, load_percent=10.0)), \
                mock.patch.object(sensors, "read_cpu_stats", return_value=CpuStats(temp_c=60.0, load_percent=20.0)):
            self.agent._live_update(active)
        for _ in range(110):
            active.aggregator.add_frame(50.0)
        active.aggregator.finish()

        samples = active.aggregator.samples()
        self.assertTrue(samples)
        self.assertEqual(samples[0].gpu_temp, 55.0)
        self.assertEqual(samples[0].cpu_temp, 60.0)
        self.assertEqual(samples[0].gpu_load, 10.0)
        self.assertEqual(samples[0].cpu_load, 20.0)

    def test_live_status_survives_sensor_failures(self) -> None:
        active = make_active(self.agent)
        with mock.patch.object(sensors, "read_gpu_stats", side_effect=RuntimeError("boom")):
            self.agent._live_update(active)

        row = self.client.live_status[-1]
        self.assertTrue(row["is_playing"])
        self.assertIsNone(row["gpu_temp"])

    def test_finish_active_ends_live_status_and_saves_game_facts(self) -> None:
        active = make_active(self.agent)
        for _ in range(110):
            active.aggregator.add_frame(50.0)
        self.agent._active = active
        self.agent._state = STATE_CAPTURING

        self.agent._finish_active("test", try_upload=False)

        row = self.client.live_status[-1]
        self.assertFalse(row["is_playing"])
        self.assertIsNone(row["current_fps"])

        self.assertEqual(len(self.uploader.saved), 1)
        record = self.uploader.saved[0]
        self.assertEqual(record.resolution, "2560x1440")
        self.assertEqual(record.display_mode, "Fullscreen")
        self.assertEqual(record.graphics_api, "DX11")
        self.assertEqual(record.game_settings, {"vsync": True, "fps_limit": 144})

    def test_finish_active_without_saved_session_still_ends_live_status(self) -> None:
        active = make_active(self.agent)
        self.agent._active = active
        self.agent._state = STATE_CAPTURING

        self.agent._finish_active("test", try_upload=False)

        self.assertFalse(self.client.live_status[-1]["is_playing"])

    def test_run_calls_live_status_idle_at_startup(self) -> None:
        self.agent._stop_event.set()
        with mock.patch.object(self.agent, "_live_status_idle") as idle:
            self.agent._run()
        idle.assert_called_once()

    def test_finish_active_calls_idle_when_session_too_short(self) -> None:
        active = make_active(self.agent)
        self.agent._active = active
        self.agent._state = STATE_CAPTURING

        with mock.patch.object(self.agent, "_live_status_idle", wraps=self.agent._live_status_idle) as idle:
            self.agent._finish_active("test", try_upload=False)

        idle.assert_called_once()
        self.assertFalse(self.client.live_status[-1]["is_playing"])

    def test_finish_active_calls_idle_when_upload_fails(self) -> None:
        active = make_active(self.agent)
        for _ in range(110):
            active.aggregator.add_frame(50.0)
        self.agent._active = active
        self.agent._state = STATE_CAPTURING

        with mock.patch.object(self.uploader, "save", side_effect=OSError("disk full")), \
                mock.patch.object(self.agent, "_live_status_idle", wraps=self.agent._live_status_idle) as idle:
            self.agent._finish_active("test", try_upload=False)

        idle.assert_called_once()
        self.assertEqual(len(self.uploader.saved), 0)
        self.assertFalse(self.client.live_status[-1]["is_playing"])

    def test_finish_active_calls_idle_when_capture_stop_fails(self) -> None:
        active = make_active(self.agent)
        active.capture = mock.Mock()
        active.capture.stop.side_effect = RuntimeError("boom")
        self.agent._active = active
        self.agent._state = STATE_CAPTURING

        with mock.patch.object(self.agent, "_live_status_idle", wraps=self.agent._live_status_idle) as idle:
            with self.assertRaises(RuntimeError):
                self.agent._finish_active("test", try_upload=False)

        idle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
