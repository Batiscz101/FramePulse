"""Payload conformance with supabase/supabase_schema.sql.

Every write payload must contain only schema columns; a bad optional field is
dropped individually instead of failing the whole request.
"""

from __future__ import annotations

import unittest

from framepulse_agent.supabase import (
    FPS_SAMPLES_COLUMNS,
    LIVE_STATUS_COLUMNS,
    SESSIONS_COLUMNS,
    SupabaseClient,
    sanitize_row,
)


class CreateSessionTests(unittest.TestCase):
    def test_create_session_payload_matches_schema(self) -> None:
        client = SupabaseClient("https://example.supabase.co", "key", session=None)
        calls: list[dict] = []

        def fake_request(method, path, **kwargs):
            calls.append({"method": method, "path": path, **kwargs})
            return None

        client._request = fake_request
        client.create_session(
            session_id="00000000-0000-0000-0000-000000000000",
            game_id="00000000-0000-0000-0000-000000000001",
            played_at="2026-11-24T20:00:00+00:00",
            avg_fps=60.0,
            min_fps=55.0,
            max_fps=70.0,
            duration_seconds=123,
            resolution="2560x1440",
            display_mode="Fullscreen",
            graphics_api="DX11",
            game_settings={"vsync": True},
            gpu_temp_avg=55.5,
            gpu_temp_max=61.0,
            gpu_load_avg=12.5,
            cpu_temp_avg=60.0,
            cpu_load_avg=30.0,
        )

        self.assertEqual(len(calls), 1)
        payload = calls[0]["json"]
        self.assertTrue(set(payload) <= SESSIONS_COLUMNS)
        self.assertEqual(payload["avg_fps"], 60.0)
        self.assertEqual(payload["duration_seconds"], 123)
        self.assertEqual(payload["game_settings"], {"vsync": True})
        self.assertEqual(payload["gpu_temp_max"], 61.0)


class SanitizeRowTests(unittest.TestCase):
    def test_keeps_schema_columns_and_drops_unknown(self) -> None:
        row = sanitize_row(LIVE_STATUS_COLUMNS, {"id": "default", "is_playing": True, "evil": 1})
        self.assertIn("id", row)
        self.assertTrue(row["is_playing"])
        self.assertNotIn("evil", row)

    def test_keeps_boolean_flag_when_column_is_boolean(self) -> None:
        row = sanitize_row(LIVE_STATUS_COLUMNS, {"id": "default", "is_playing": False, "gpu_temp": None})
        self.assertIs(row["is_playing"], False)
        self.assertIn("gpu_temp", row)

    def test_numbers_converted_and_invalid_dropped(self) -> None:
        row = sanitize_row(LIVE_STATUS_COLUMNS, {"current_fps": 60, "gpu_temp": "not-a-number", "cpu_temp": float("nan")})
        self.assertEqual(row["current_fps"], 60.0)
        self.assertNotIn("gpu_temp", row)
        self.assertNotIn("cpu_temp", row)


class SupabaseClientPayloadTests(unittest.TestCase):
    def _client(self):
        return SupabaseClient("https://example.supabase.co", "key", session=None)

    def test_upsert_live_status_payload_matches_schema(self) -> None:
        client = self._client()
        calls: list[dict] = []

        def fake_request(method, path, **kwargs):
            calls.append({"method": method, "path": path, **kwargs})
            return [{"id": "default"}]

        client._request = fake_request
        client.upsert_live_status(
            {
                "id": "default",
                "is_playing": True,
                "game_name": "Game",
                "process_name": "game.exe",
                "current_fps": 61.5,
                "gpu_temp": "not-a-number",
                "cpu_temp": 60.0,
                "gpu_load": 10.0,
                "cpu_load": 20.0,
                "resolution": "2560x1440",
                "graphics_api": "DX11",
                "updated_at": "2026-11-24T20:00:00+00:00",
                "nonsense_column": 42,
            }
        )

        payload = calls[0]["json"]
        self.assertTrue(set(payload) <= LIVE_STATUS_COLUMNS)
        self.assertNotIn("nonsense_column", payload)
        self.assertTrue(payload["is_playing"])
        # The bad optional field is dropped; the rest of the update survives.
        self.assertNotIn("gpu_temp", payload)
        self.assertEqual(payload["cpu_load"], 20.0)

    def test_insert_samples_payload_matches_schema(self) -> None:
        client = self._client()
        calls: list[dict] = []

        def fake_request(method, path, **kwargs):
            calls.append({"method": method, "path": path, **kwargs})
            return None

        client._request = fake_request
        client.insert_samples(
            [
                {"session_id": "s1", "timestamp_offset": 2.0, "fps": 60.0, "gpu_temp": None},
                {"session_id": "s1", "timestamp_offset": "4", "fps": 58.5, "unexpected": "x"},
            ]
        )

        self.assertEqual(len(calls), 1)
        rows = calls[0]["json"]
        for row in rows:
            self.assertTrue(set(row) <= FPS_SAMPLES_COLUMNS)
            self.assertEqual(row["session_id"], "s1")
        self.assertEqual(rows[1]["timestamp_offset"], 4.0)


if __name__ == "__main__":
    unittest.main()
