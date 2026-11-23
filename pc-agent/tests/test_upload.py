from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from framepulse_agent.metrics import FpsMetrics, Sample
from framepulse_agent.supabase import SupabaseError
from framepulse_agent.upload import SessionRecord, Uploader, build_record, chunked


def metrics() -> FpsMetrics:
    return FpsMetrics(
        avg_fps=59.941,
        min_fps=48.0,
        max_fps=61.2,
        duration_seconds=123.4,
        frame_count=7000,
        sample_count=2,
    )


class BuildRecordTests(unittest.TestCase):
    def test_builds_session_values(self) -> None:
        record = build_record(
            process_name="Cyberpunk2077.exe",
            name="Cyberpunk 2077",
            started_at=datetime(2026, 11, 18, 20, 30, tzinfo=timezone.utc),
            metrics=metrics(),
            samples=[Sample(0.0, 60.0), Sample(2.0, 59.941)],
        )

        self.assertEqual(record.process_name, "Cyberpunk2077.exe")
        self.assertEqual(record.name, "Cyberpunk 2077")
        self.assertEqual(record.played_at, "2026-11-18T20:30:00+00:00")
        self.assertAlmostEqual(record.avg_fps, 59.94, places=2)
        self.assertAlmostEqual(record.min_fps, 48.0, places=2)
        self.assertAlmostEqual(record.max_fps, 61.2, places=2)
        self.assertEqual(record.duration_seconds, 123)

        self.assertEqual(len(record.samples), 2)
        self.assertEqual(record.samples[1]["timestamp_offset"], 2.0)
        self.assertEqual(record.samples[1]["fps"], 59.94)

    def test_local_time_is_converted_to_utc(self) -> None:
        local = datetime(2026, 11, 18, 12, 0).astimezone()
        record = build_record(
            process_name="game.exe",
            name="Game",
            started_at=local,
            metrics=metrics(),
            samples=[],
        )
        self.assertTrue(record.played_at.endswith("+00:00"))

    def test_build_record_carries_game_facts_and_telemetry(self) -> None:
        record = build_record(
            process_name="game.exe",
            name="Game",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            metrics=metrics(),
            samples=[Sample(0.0, 60.0, gpu_temp=55.0, cpu_temp=60.0, gpu_load=12.5, cpu_load=30.0)],
            resolution="2560x1440",
            display_mode="Fullscreen",
            graphics_api="DX11",
            game_settings={"vsync": True, "fps_limit": 144},
            gpu_temp_avg=55.0,
            gpu_temp_max=61.0,
            gpu_load_avg=12.5,
            cpu_temp_avg=60.0,
            cpu_load_avg=30.0,
        )

        self.assertEqual(record.resolution, "2560x1440")
        self.assertEqual(record.display_mode, "Fullscreen")
        self.assertEqual(record.graphics_api, "DX11")
        self.assertEqual(record.game_settings, {"vsync": True, "fps_limit": 144})
        self.assertEqual(record.gpu_temp_avg, 55.0)
        self.assertEqual(record.gpu_temp_max, 61.0)
        self.assertEqual(record.gpu_load_avg, 12.5)
        self.assertEqual(record.cpu_temp_avg, 60.0)
        self.assertEqual(record.cpu_load_avg, 30.0)
        self.assertEqual(record.samples[0]["gpu_temp"], 55.0)
        self.assertEqual(record.samples[0]["cpu_temp"], 60.0)
        self.assertEqual(record.samples[0]["gpu_load"], 12.5)
        self.assertEqual(record.samples[0]["cpu_load"], 30.0)

        restored = SessionRecord.from_dict(json.loads(record.to_json()))
        self.assertEqual(restored.resolution, "2560x1440")
        self.assertEqual(restored.game_settings, {"vsync": True, "fps_limit": 144})
        self.assertEqual(restored.gpu_temp_max, 61.0)
        self.assertEqual(restored.samples[0]["gpu_load"], 12.5)


class SessionRecordTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        record = build_record(
            process_name="game.exe",
            name="Game",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            metrics=metrics(),
            samples=[Sample(0.0, 60.0)],
        )
        record.session_id = "00000000-0000-0000-0000-000000000000"

        restored = SessionRecord.from_dict(__import__("json").loads(record.to_json()))

        self.assertEqual(restored.process_name, record.process_name)
        self.assertEqual(restored.name, record.name)
        self.assertEqual(restored.session_id, record.session_id)
        self.assertEqual(restored.duration_seconds, record.duration_seconds)
        self.assertEqual(restored.samples, record.samples)

    def test_from_dict_defaults(self) -> None:
        record = SessionRecord.from_dict(
            {
                "process_name": "game.exe",
                "name": "Game",
                "played_at": "2026-01-01T00:00:00+00:00",
            }
        )
        self.assertEqual(record.samples, [])
        self.assertEqual(record.duration_seconds, 0)
        self.assertIsNone(record.session_id)


class ChunkedTests(unittest.TestCase):
    def test_splits_evenly(self) -> None:
        self.assertEqual([len(batch) for batch in chunked(range(10), 3)], [3, 3, 3, 1])

    def test_empty(self) -> None:
        self.assertEqual(list(chunked([], 5)), [])

    def test_smaller_than_chunk(self) -> None:
        self.assertEqual([len(batch) for batch in chunked([1, 2], 10)], [2])


class FakeClient:
    """Minimal SupabaseClient stand-in for upload tests."""

    def __init__(self, *, fail_once: bool = False, fail_always: bool = False) -> None:
        self.games: dict[str, dict] = {}
        self.sessions: dict[str, dict] = {}
        self.samples: list[dict] = []
        self.delete_calls = 0
        self._fail_once = fail_once
        self._fail_always = fail_always

    def find_game(self, process_name: str):
        return self.games.get(process_name)

    def create_game(self, name: str, process_name: str, game_id: str | None = None):
        row = {"id": game_id or str(uuid.uuid4()), "name": name, "process_name": process_name}
        self.games[process_name] = row
        return row

    def create_session(self, **kwargs) -> None:
        self.sessions[kwargs["session_id"]] = kwargs

    def delete_samples(self, session_id: str) -> None:
        self.delete_calls += 1
        self.samples = [row for row in self.samples if row["session_id"] != session_id]

    def insert_samples(self, rows: list[dict]) -> None:
        if self._fail_always:
            raise SupabaseError("boom", status=500)
        if self._fail_once:
            self._fail_once = False
            raise SupabaseError("duplicate", status=409, code="23505")
        self.samples.extend(rows)


class UploaderTests(unittest.TestCase):
    def _record(self) -> SessionRecord:
        record = build_record(
            process_name="game.exe",
            name="Game",
            started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            metrics=FpsMetrics(60.0, 50.0, 70.0, 30.0, 1800, 3),
            samples=[Sample(0.0, 60.0), Sample(2.0, 61.0), Sample(4.0, 59.0)],
        )
        return record

    def test_upload_creates_game_session_and_samples(self) -> None:
        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            uploader = Uploader(client, Path(tmp) / "outbox", chunk_size=2)
            record = self._record()

            self.assertTrue(uploader.submit(record))

            self.assertEqual(uploader.pending_count(), 0)
            self.assertIn("game.exe", client.games)
            self.assertIn(record.session_id, client.sessions)
            self.assertEqual(len(client.samples), 3)
            self.assertEqual(client.delete_calls, 1)

    def test_upload_sends_sample_telemetry(self) -> None:
        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            uploader = Uploader(client, Path(tmp) / "outbox", chunk_size=10)
            record = build_record(
                process_name="game.exe",
                name="Game",
                started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                metrics=FpsMetrics(60.0, 50.0, 70.0, 30.0, 1800, 3),
                samples=[Sample(0.0, 60.0, gpu_temp=55.0, cpu_temp=60.0, gpu_load=12.0, cpu_load=30.0)],
            )

            self.assertTrue(uploader.submit(record))

            row = client.samples[0]
            self.assertEqual(row["session_id"], record.session_id)
            self.assertEqual(row["timestamp_offset"], 0.0)
            self.assertEqual(row["fps"], 60.0)
            self.assertEqual(row["gpu_temp"], 55.0)
            self.assertEqual(row["cpu_temp"], 60.0)
            self.assertEqual(row["gpu_load"], 12.0)
            self.assertEqual(row["cpu_load"], 30.0)

    def test_duplicate_samples_are_rewritten(self) -> None:
        client = FakeClient(fail_once=True)
        with tempfile.TemporaryDirectory() as tmp:
            uploader = Uploader(client, Path(tmp) / "outbox", chunk_size=2)
            record = self._record()

            self.assertTrue(uploader.submit(record))

            self.assertEqual(len(client.samples), 3)
            self.assertEqual(client.delete_calls, 2)

    def test_failed_upload_stays_in_outbox(self) -> None:
        client = FakeClient(fail_always=True)
        with tempfile.TemporaryDirectory() as tmp:
            uploader = Uploader(client, Path(tmp) / "outbox", chunk_size=2)
            record = self._record()

            self.assertFalse(uploader.submit(record))
            self.assertEqual(uploader.pending_count(), 1)
            self.assertIsNotNone(uploader.last_error)

            files = list((Path(tmp) / "outbox").glob("*.json"))
            self.assertEqual(len(files), 1)
            saved = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(saved["process_name"], "game.exe")
            self.assertIsNotNone(saved["session_id"])

    def test_flush_uploads_pending_records(self) -> None:
        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp) / "outbox"
            uploader = Uploader(client, outbox, chunk_size=10)
            record = self._record()
            record.session_id = str(uuid.uuid4())
            uploader.save(record)

            uploaded, failed = uploader.flush()

            self.assertEqual((uploaded, failed), (1, 0))
            self.assertEqual(uploader.pending_count(), 0)
            self.assertIn(record.session_id, client.sessions)


if __name__ == "__main__":
    unittest.main()
